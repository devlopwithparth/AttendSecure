from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash,
    jsonify, send_file, current_app
)

from extensions import db
from models import User, LectureSession, Attendance, Marks
from utils.auth_utils import role_required
from utils.qr_utils import verify_qr_token
from utils.geo_utils import is_within_radius
from utils.export_utils import export_to_excel, export_to_pdf
from utils.face_utils import compare_student_faces, save_selfie_from_data_url

student_bp = Blueprint("student", __name__, template_folder="../templates/student")


@student_bp.route("/dashboard")
@role_required("student")
def dashboard():
    student_id = session["user_id"]
    total_present = Attendance.query.filter_by(student_id=student_id).count()
    recent = (
        Attendance.query.filter_by(student_id=student_id)
        .order_by(Attendance.scanned_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "student/dashboard.html",
        name=session.get("name"),
        total_present=total_present,
        recent=recent,
    )


@student_bp.route("/scan")
@role_required("student")
def scan():
    student = User.query.get(session["user_id"])
    return render_template("student/scan.html", has_profile_photo=bool(student.profile_photo))


@student_bp.route("/selfie/verify", methods=["POST"])
@role_required("student")
def selfie_verify():
    student = User.query.get(session["user_id"])
    if not student or not student.profile_photo:
        return jsonify({
            "success": False,
            "message": "No registration photo found for this student account.",
        }), 400

    data = request.get_json(force=True)
    try:
        selfie_path = save_selfie_from_data_url(
            data.get("selfie"),
            student.id,
            current_app.config["UPLOAD_FOLDER"],
        )
        matched, score = compare_student_faces(
            student.profile_photo,
            selfie_path,
            current_app.config["UPLOAD_FOLDER"],
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except OSError:
        return jsonify({"success": False, "message": "Could not compare the selfie with the registration photo."}), 400

    if not matched:
        session.pop("selfie_verified_at", None)
        session.pop("selfie_photo", None)
        session.pop("face_match_score", None)
        return jsonify({
            "success": False,
            "message": "Selfie did not match the registration photo. Please try again in good light.",
        }), 403

    session["selfie_verified_at"] = datetime.utcnow().isoformat()
    session["selfie_photo"] = selfie_path
    session["face_match_score"] = score
    return jsonify({"success": True, "message": "Selfie verified. You can now scan the faculty QR."})


@student_bp.route("/scan/submit", methods=["POST"])
@role_required("student")
def scan_submit():
    """Called via AJAX from the scanner page with the decoded QR token + browser GPS coords."""
    data = request.get_json(force=True)
    token = data.get("token")
    lat = data.get("latitude")
    lon = data.get("longitude")

    if not token:
        return jsonify({"success": False, "message": "No QR token received."}), 400
    if lat is None or lon is None:
        return jsonify({"success": False, "message": "Location access is required to mark attendance."}), 400
    selfie_verified_at = session.get("selfie_verified_at")
    if not selfie_verified_at:
        return jsonify({"success": False, "message": "Please verify your selfie before scanning the QR."}), 400
    try:
        selfie_verified_time = datetime.fromisoformat(selfie_verified_at)
    except ValueError:
        session.pop("selfie_verified_at", None)
        return jsonify({"success": False, "message": "Please verify your selfie again."}), 400
    if (datetime.utcnow() - selfie_verified_time).total_seconds() > 300:
        session.pop("selfie_verified_at", None)
        return jsonify({"success": False, "message": "Selfie verification expired. Please verify again."}), 400

    session_id, error = verify_qr_token(token)
    if error:
        return jsonify({"success": False, "message": error}), 400

    lecture = LectureSession.query.get(session_id)
    if not lecture:
        return jsonify({"success": False, "message": "Lecture session not found."}), 404
    if not lecture.is_active or datetime.utcnow() > lecture.expires_at:
        return jsonify({"success": False, "message": "This lecture session has ended."}), 400

    student_id = session["user_id"]

    already = Attendance.query.filter_by(session_id=session_id, student_id=student_id).first()
    if already:
        return jsonify({"success": False, "message": "Attendance already marked for this lecture."}), 400

    within, distance = is_within_radius(
        float(lat), float(lon), lecture.latitude, lecture.longitude, lecture.radius_meters
    )
    if not within:
        return jsonify({
            "success": False,
            "message": f"You appear to be {round(distance)}m from the classroom "
                       f"(allowed radius: {int(lecture.radius_meters)}m). Attendance not marked."
        }), 400

    record = Attendance(
        session_id=session_id,
        student_id=student_id,
        latitude=float(lat),
        longitude=float(lon),
        distance_meters=distance,
        status="present",
        selfie_photo=session.get("selfie_photo"),
        face_match_score=session.get("face_match_score"),
    )
    db.session.add(record)
    db.session.commit()
    session.pop("selfie_verified_at", None)
    session.pop("selfie_photo", None)
    session.pop("face_match_score", None)

    return jsonify({
        "success": True,
        "message": f"Attendance marked for {lecture.subject} ({lecture.class_section}).",
    })


# ---------------------------------------------------- ATTENDANCE ANALYSIS --
@student_bp.route("/attendance")
@role_required("student")
def attendance():
    student_id = session["user_id"]
    records = (
        Attendance.query.filter_by(student_id=student_id)
        .order_by(Attendance.scanned_at.desc())
        .all()
    )

    # group by subject for a simple percentage view
    subject_counts = {}
    for r in records:
        subj = r.session.subject
        subject_counts[subj] = subject_counts.get(subj, 0) + 1

    return render_template("student/attendance.html", records=records, subject_counts=subject_counts)


@student_bp.route("/attendance/export/excel")
@role_required("student")
def export_attendance_excel():
    student_id = session["user_id"]
    records = (
        Attendance.query.filter_by(student_id=student_id).order_by(Attendance.scanned_at).all()
    )
    headers = ["Subject", "Class", "Scanned At", "Status"]
    rows = [[r.session.subject, r.session.class_section,
              r.scanned_at.strftime("%Y-%m-%d %H:%M:%S"), r.status] for r in records]
    buf = export_to_excel(headers, rows, sheet_title="My Attendance")
    return send_file(buf, as_attachment=True, download_name="my_attendance.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@student_bp.route("/attendance/export/pdf")
@role_required("student")
def export_attendance_pdf():
    student_id = session["user_id"]
    records = (
        Attendance.query.filter_by(student_id=student_id).order_by(Attendance.scanned_at).all()
    )
    headers = ["Subject", "Class", "Scanned At", "Status"]
    rows = [[r.session.subject, r.session.class_section,
              r.scanned_at.strftime("%Y-%m-%d %H:%M:%S"), r.status] for r in records]
    buf = export_to_pdf("My Attendance Record", headers, rows)
    return send_file(buf, as_attachment=True, download_name="my_attendance.pdf", mimetype="application/pdf")


# ------------------------------------------------------------------ MARKS --
@student_bp.route("/marks")
@role_required("student")
def marks():
    student_id = session["user_id"]
    entries = Marks.query.filter_by(student_id=student_id).order_by(Marks.uploaded_at.desc()).all()
    return render_template("student/marks.html", entries=entries)


@student_bp.route("/marks/export/excel")
@role_required("student")
def export_marks_excel():
    student_id = session["user_id"]
    entries = Marks.query.filter_by(student_id=student_id).order_by(Marks.uploaded_at).all()
    headers = ["Subject", "Exam", "Marks Obtained", "Max Marks", "Uploaded At"]
    rows = [[e.subject, e.exam_type, e.marks_obtained, e.max_marks,
              e.uploaded_at.strftime("%Y-%m-%d %H:%M:%S")] for e in entries]
    buf = export_to_excel(headers, rows, sheet_title="My Marks")
    return send_file(buf, as_attachment=True, download_name="my_marks.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
