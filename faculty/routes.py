from datetime import datetime, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash,
    jsonify, send_file, current_app
)

from extensions import db
from models import User, LectureSession, Attendance, Marks
from utils.auth_utils import role_required
from utils.qr_utils import make_qr_token, verify_qr_token, qr_token_to_image_base64
from utils.export_utils import export_to_excel, export_to_pdf

faculty_bp = Blueprint("faculty", __name__, template_folder="../templates/faculty")


@faculty_bp.route("/dashboard")
@role_required("faculty")
def dashboard():
    faculty_id = session["user_id"]
    sessions = (
        LectureSession.query.filter_by(faculty_id=faculty_id)
        .order_by(LectureSession.created_at.desc())
        .limit(20)
        .all()
    )

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    today_sessions = [s for s in sessions if today_start <= s.created_at < today_end]

    # the session a faculty member is most likely watching right now
    live_session = next((s for s in today_sessions if s.is_active), None)

    total_students = User.query.filter_by(role="student").count()

    todays_attendance = (
        Attendance.query.join(LectureSession, Attendance.session_id == LectureSession.id)
        .filter(
            LectureSession.faculty_id == faculty_id,
            Attendance.scanned_at >= today_start,
            Attendance.scanned_at < today_end,
        )
        .all()
    )
    present_today = len(todays_attendance)
    verified_today = sum(1 for a in todays_attendance if a.face_match_score is not None)
    absent_today = max(total_students - present_today, 0)

    attendance_percentage = round((present_today / total_students) * 100, 1) if total_students else 0
    verification_rate = round((verified_today / present_today) * 100, 1) if present_today else 0

    # ---- recent activity feed (derived from real attendance rows) ----
    recent_attendance = (
        Attendance.query.join(LectureSession, Attendance.session_id == LectureSession.id)
        .filter(LectureSession.faculty_id == faculty_id)
        .order_by(Attendance.scanned_at.desc())
        .limit(8)
        .all()
    )
    activities = []
    for a in recent_attendance:
        activities.append({
            "type": "verified" if a.face_match_score is not None else "present",
            "text": f"{a.student.name} marked present in {a.session.subject}"
                    + (" · selfie verified" if a.face_match_score is not None else ""),
            "time": a.scanned_at,
        })

    return render_template(
        "faculty/dashboard.html",
        sessions=sessions,
        today_sessions=today_sessions,
        live_session=live_session,
        name=session.get("name"),
        stats={
            "total_students": total_students,
            "sessions_today": len(today_sessions),
            "present_today": present_today,
            "absent_today": absent_today,
            "attendance_percentage": attendance_percentage,
            "verification_rate": verification_rate,
            "verified_today": verified_today,
        },
        activities=activities,
    )


# --------------------------------------------------- START A LECTURE / QR --
@faculty_bp.route("/session/start", methods=["POST"])
@role_required("faculty")
def start_session():
    faculty_id = session["user_id"]
    subject = request.form.get("subject", "").strip()
    class_section = request.form.get("class_section", "").strip()
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")
    radius = request.form.get("radius") or current_app.config["DEFAULT_GEOFENCE_RADIUS_METERS"]
    duration = int(request.form.get("duration") or current_app.config["LECTURE_SESSION_MAX_MINUTES"])

    if not subject or not class_section or not latitude or not longitude:
        flash("Subject, class, and your current location are required to start a session.", "error")
        return redirect(url_for("faculty.dashboard"))

    lecture = LectureSession(
        faculty_id=faculty_id,
        subject=subject,
        class_section=class_section,
        latitude=float(latitude),
        longitude=float(longitude),
        radius_meters=float(radius),
        expires_at=datetime.utcnow() + timedelta(minutes=duration),
        is_active=True,
    )
    db.session.add(lecture)
    db.session.commit()
    return redirect(url_for("faculty.session_view", session_id=lecture.id))


@faculty_bp.route("/session/<session_id>")
@role_required("faculty")
def session_view(session_id):
    lecture = LectureSession.query.get_or_404(session_id)
    if lecture.faculty_id != session["user_id"]:
        flash("Not authorized.", "error")
        return redirect(url_for("faculty.dashboard"))
    return render_template(
        "faculty/session.html",
        lecture=lecture,
        qr_refresh_seconds=current_app.config["QR_TOKEN_VALID_SECONDS"],
    )


@faculty_bp.route("/session/<session_id>/qr-token")
@role_required("faculty")
def session_qr_token(session_id):
    """AJAX polled by the session page to keep the QR rotating (anti screenshot-sharing)."""
    lecture = LectureSession.query.get_or_404(session_id)
    if lecture.faculty_id != session["user_id"]:
        return jsonify({"error": "not authorized"}), 403

    if not lecture.is_active or datetime.utcnow() > lecture.expires_at:
        return jsonify({"error": "session_closed"}), 400

    token = make_qr_token(lecture.id)
    image_b64 = qr_token_to_image_base64(token)
    return jsonify({
        "image": image_b64,
        "expires_in": current_app.config["QR_TOKEN_VALID_SECONDS"],
    })


@faculty_bp.route("/session/<session_id>/attendance-data")
@role_required("faculty")
def session_attendance_data(session_id):
    lecture = LectureSession.query.get_or_404(session_id)
    if lecture.faculty_id != session["user_id"]:
        return jsonify({"error": "not authorized"}), 403

    records = (
        Attendance.query.filter_by(session_id=session_id)
        .order_by(Attendance.scanned_at.desc())
        .all()
    )
    data = [
        {
            "name": r.student.name,
            "roll_no": r.student.roll_no,
            "time": r.scanned_at.strftime("%H:%M:%S"),
            "distance": round(r.distance_meters, 1) if r.distance_meters is not None else None,
        }
        for r in records
    ]
    return jsonify({"count": len(data), "records": data, "is_active": lecture.is_active})


@faculty_bp.route("/session/<session_id>/close", methods=["POST"])
@role_required("faculty")
def close_session(session_id):
    lecture = LectureSession.query.get_or_404(session_id)
    if lecture.faculty_id != session["user_id"]:
        flash("Not authorized.", "error")
        return redirect(url_for("faculty.dashboard"))
    lecture.is_active = False
    db.session.commit()
    flash("Lecture session closed.", "success")
    return redirect(url_for("faculty.session_view", session_id=session_id))


# --------------------------------------------------------------- EXPORTS --
def _session_export_rows(lecture):
    records = (
        Attendance.query.filter_by(session_id=lecture.id).order_by(Attendance.scanned_at).all()
    )
    headers = ["Name", "Roll No", "Department", "Scanned At", "Distance (m)"]
    rows = [
        [r.student.name, r.student.roll_no, r.student.department,
         r.scanned_at.strftime("%Y-%m-%d %H:%M:%S"),
         round(r.distance_meters, 1) if r.distance_meters is not None else ""]
        for r in records
    ]
    return headers, rows


@faculty_bp.route("/session/<session_id>/export/excel")
@role_required("faculty")
def export_session_excel(session_id):
    lecture = LectureSession.query.get_or_404(session_id)
    if lecture.faculty_id != session["user_id"]:
        flash("Not authorized.", "error")
        return redirect(url_for("faculty.dashboard"))
    headers, rows = _session_export_rows(lecture)
    buf = export_to_excel(headers, rows, sheet_title=lecture.subject)
    filename = f"attendance_{lecture.subject}_{lecture.created_at.strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(buf, as_attachment=True, download_name=filename,
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@faculty_bp.route("/session/<session_id>/export/pdf")
@role_required("faculty")
def export_session_pdf(session_id):
    lecture = LectureSession.query.get_or_404(session_id)
    if lecture.faculty_id != session["user_id"]:
        flash("Not authorized.", "error")
        return redirect(url_for("faculty.dashboard"))
    headers, rows = _session_export_rows(lecture)
    buf = export_to_pdf(f"Attendance — {lecture.subject} ({lecture.class_section})", headers, rows)
    filename = f"attendance_{lecture.subject}_{lecture.created_at.strftime('%Y%m%d_%H%M')}.pdf"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/pdf")


# ----------------------------------------------------------------- MARKS --
@faculty_bp.route("/marks", methods=["GET", "POST"])
@role_required("faculty")
def marks():
    faculty_id = session["user_id"]

    if request.method == "POST":
        student_id = request.form.get("student_id")
        subject = request.form.get("subject", "").strip()
        exam_type = request.form.get("exam_type", "").strip()
        marks_obtained = request.form.get("marks_obtained")
        max_marks = request.form.get("max_marks")

        if not all([student_id, subject, exam_type, marks_obtained, max_marks]):
            flash("All fields are required.", "error")
            return redirect(url_for("faculty.marks"))

        entry = Marks(
            faculty_id=faculty_id,
            student_id=student_id,
            subject=subject,
            exam_type=exam_type,
            marks_obtained=float(marks_obtained),
            max_marks=float(max_marks),
        )
        db.session.add(entry)
        db.session.commit()
        flash("Marks uploaded successfully.", "success")
        return redirect(url_for("faculty.marks"))

    students = User.query.filter_by(role="student").order_by(User.name).all()
    entries = (
        Marks.query.filter_by(faculty_id=faculty_id).order_by(Marks.uploaded_at.desc()).limit(50).all()
    )
    return render_template("faculty/marks.html", students=students, entries=entries)


@faculty_bp.route("/marks/export/excel")
@role_required("faculty")
def export_marks_excel():
    faculty_id = session["user_id"]
    entries = Marks.query.filter_by(faculty_id=faculty_id).order_by(Marks.uploaded_at).all()
    headers = ["Student", "Roll No", "Subject", "Exam", "Marks Obtained", "Max Marks", "Uploaded At"]
    rows = [
        [e.student.name, e.student.roll_no, e.subject, e.exam_type, e.marks_obtained,
         e.max_marks, e.uploaded_at.strftime("%Y-%m-%d %H:%M:%S")]
        for e in entries
    ]
    buf = export_to_excel(headers, rows, sheet_title="Marks")
    return send_file(buf, as_attachment=True, download_name="marks_export.xlsx",
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
