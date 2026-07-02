import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # --- Core ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-this-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'attendance.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- OTP ---
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 5
    OTP_MAX_ATTEMPTS = 3
    OTP_RESEND_COOLDOWN_SECONDS = 60

    # --- Session tokens ---
    SESSION_TOKEN_EXPIRY = timedelta(hours=8)

    # --- QR / Geofencing ---
    QR_TOKEN_VALID_SECONDS = 25          # rotating token lifetime (anti-screenshot-sharing)
    LECTURE_SESSION_MAX_MINUTES = 90     # how long a lecture attendance window stays open
    DEFAULT_GEOFENCE_RADIUS_METERS = 50  # how close a student must be to the faculty's location
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "static"))

    # --- Mail (for sending OTP emails) ---
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "").replace(" ", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", os.environ.get("MAIL_USERNAME", ""))

    # If True, OTPs are printed to console instead of emailed (useful for local dev/testing)
    OTP_DEV_MODE = os.environ.get("OTP_DEV_MODE", "true").lower() == "true"
