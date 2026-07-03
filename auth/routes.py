import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app

from extensions import db, bcrypt
from models import User, LoginLog
from utils.otp_utils import create_and_send_otp, verify_otp
from utils.auth_utils import get_client_fingerprint
from utils.face_utils import save_student_reference_photo

auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


# ---------------------------------------------------------------- SIGNUP ---
@auth_bp.route("/signup/<role>", methods=["GET", "POST"])
def signup(role):
    if role not in ("student", "faculty"):
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("auth.signup", role=role))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth.signup", role=role))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("auth.signup", role=role))

        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
            return redirect(url_for("auth.login"))

        password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

        user = User(
            id=str(uuid.uuid4()),
            name=name,
            email=email,
            password_hash=password_hash,
            role=role,
            is_verified=False,
        )
        if role == "student":
            user.roll_no = request.form.get("roll_no", "").strip()
            user.department = request.form.get("department", "").strip()
            user.semester = request.form.get("semester", "").strip()
            try:
                user.profile_photo = save_student_reference_photo(
                    request.files.get("profile_photo"),
                    user.id,
                    current_app.config["UPLOAD_FOLDER"],
                )
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("auth.signup", role=role))
        else:
            user.employee_id = request.form.get("employee_id", "").strip()
            user.department = request.form.get("department", "").strip()

        db.session.add(user)
        db.session.commit()

        create_and_send_otp(email, purpose="signup")
        session["pending_email"] = email
        session["pending_purpose"] = "signup"
        flash("An OTP has been sent to your email. Please verify to activate your account.", "info")
        return redirect(url_for("auth.verify_otp_route"))

    return render_template(f"auth/signup_{role}.html")


# ------------------------------------------------------------------ LOGIN --
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not bcrypt.check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login"))

        if not user.is_verified:
            flash("Please verify your account first.", "error")
            create_and_send_otp(email, purpose="signup")
            session["pending_email"] = email
            session["pending_purpose"] = "signup"
            return redirect(url_for("auth.verify_otp_route"))

        # Password correct -> now require OTP to complete login (2FA)
        create_and_send_otp(email, purpose="login")
        session["pending_email"] = email
        session["pending_purpose"] = "login"
        session["pending_user_id"] = user.id
        session["pending_remember"] = request.form.get("remember_me") == "on"
        flash("An OTP has been sent to your email to complete login.", "info")
        return redirect(url_for("auth.verify_otp_route"))

    return render_template("auth/login.html")


# ------------------------------------------------------------- VERIFY OTP --
@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp_route():
    email = session.get("pending_email")
    purpose = session.get("pending_purpose")

    if not email or not purpose:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        code = request.form.get("otp", "").strip()
        ok, message = verify_otp(email, purpose, code)

        if not ok:
            flash(message, "error")
            return redirect(url_for("auth.verify_otp_route"))

        user = User.query.filter_by(email=email).first()

        if purpose == "signup":
            user.is_verified = True
            db.session.commit()
            flash("Account verified! Please log in.", "success")
            session.pop("pending_email", None)
            session.pop("pending_purpose", None)
            return redirect(url_for("auth.login"))

        # purpose == login -> establish session, log device info
        remember = session.pop("pending_remember", False)
        session["user_id"] = user.id
        session["role"] = user.role
        session["name"] = user.name
        session.pop("pending_email", None)
        session.pop("pending_purpose", None)
        session.pop("pending_user_id", None)

        # "Remember me" checked -> session cookie lasts PERMANENT_SESSION_LIFETIME (30 days,
        # rolling). Unchecked -> normal browser-session cookie that clears on browser close.
        session.permanent = bool(remember)

        log = LoginLog(
            user_id=user.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
            device_fingerprint=get_client_fingerprint(),
        )
        db.session.add(log)
        db.session.commit()

        flash(f"Welcome back, {user.name}!", "success")
        if user.role == "faculty":
            return redirect(url_for("faculty.dashboard"))
        return redirect(url_for("student.dashboard"))

    cooldown = current_app.config["OTP_RESEND_COOLDOWN_SECONDS"]
    return render_template("auth/verify_otp.html", email=email, cooldown=cooldown)


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    email = session.get("pending_email")
    purpose = session.get("pending_purpose")
    if not email or not purpose:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("auth.login"))

    create_and_send_otp(email, purpose)
    flash("A new OTP has been sent.", "info")
    return redirect(url_for("auth.verify_otp_route"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
