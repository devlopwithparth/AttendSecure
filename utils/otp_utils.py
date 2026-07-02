import random
import string
from datetime import datetime, timedelta

from extensions import db, bcrypt, mail
from models import OTP
from flask import current_app
from flask_mail import Message


def generate_otp(length=6):
    return "".join(random.choices(string.digits, k=length))


def create_and_send_otp(email, purpose):
    """Generates a fresh OTP, invalidates old ones for this email+purpose, stores hash, sends email."""
    cfg = current_app.config

    # invalidate previous unconsumed OTPs for this email/purpose
    OTP.query.filter_by(email=email, purpose=purpose, consumed=False).update({"consumed": True})

    otp_code = generate_otp(cfg["OTP_LENGTH"])
    otp_hash = bcrypt.generate_password_hash(otp_code).decode("utf-8")
    expires_at = datetime.utcnow() + timedelta(minutes=cfg["OTP_EXPIRY_MINUTES"])

    record = OTP(email=email, otp_hash=otp_hash, purpose=purpose, expires_at=expires_at)
    db.session.add(record)
    db.session.commit()

    if cfg.get("OTP_DEV_MODE", True):
        # Dev/testing mode: no real mail server needed, print to console/log instead
        print(f"[DEV OTP] Email={email} Purpose={purpose} OTP={otp_code} (expires in {cfg['OTP_EXPIRY_MINUTES']}m)")
    else:
        msg = Message(
            subject="Your OTP Code",
            recipients=[email],
            body=f"Your OTP is {otp_code}. It expires in {cfg['OTP_EXPIRY_MINUTES']} minutes. "
                 f"Do not share this code with anyone.",
        )
        mail.send(msg)

    return record


def verify_otp(email, purpose, submitted_code):
    """Returns (success: bool, message: str)."""
    cfg = current_app.config
    record = (
        OTP.query.filter_by(email=email, purpose=purpose, consumed=False)
        .order_by(OTP.created_at.desc())
        .first()
    )

    if not record:
        return False, "No active OTP found. Please request a new one."

    if datetime.utcnow() > record.expires_at:
        record.consumed = True
        db.session.commit()
        return False, "OTP expired. Please request a new one."

    if record.attempts >= cfg["OTP_MAX_ATTEMPTS"]:
        record.consumed = True
        db.session.commit()
        return False, "Too many incorrect attempts. Please request a new OTP."

    if not bcrypt.check_password_hash(record.otp_hash, submitted_code):
        record.attempts += 1
        db.session.commit()
        remaining = cfg["OTP_MAX_ATTEMPTS"] - record.attempts
        return False, f"Incorrect OTP. {remaining} attempt(s) remaining."

    record.consumed = True
    db.session.commit()
    return True, "OTP verified successfully."
