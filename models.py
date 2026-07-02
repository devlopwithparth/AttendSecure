import uuid
from datetime import datetime
from extensions import db


def gen_uuid():
    return str(uuid.uuid4())


class User(db.Model):
    """Common table for both faculty and students, distinguished by `role`."""
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'student' or 'faculty'

    # student-only fields
    roll_no = db.Column(db.String(50), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    semester = db.Column(db.String(20), nullable=True)
    profile_photo = db.Column(db.String(255), nullable=True)

    # faculty-only fields
    employee_id = db.Column(db.String(50), nullable=True)

    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "roll_no": self.roll_no,
            "department": self.department,
            "semester": self.semester,
            "employee_id": self.employee_id,
        }


class OTP(db.Model):
    __tablename__ = "otps"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    otp_hash = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(20), nullable=False)  # 'signup' or 'login'
    attempts = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    consumed = db.Column(db.Boolean, default=False)


class LoginLog(db.Model):
    """Audit trail of every login/device used — supports the 'device-aware' security model."""
    __tablename__ = "login_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    ip_address = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    device_fingerprint = db.Column(db.String(255))
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    login_time = db.Column(db.DateTime, default=datetime.utcnow)


class LectureSession(db.Model):
    """Created when a faculty member 'starts' a lecture and generates a QR."""
    __tablename__ = "lecture_sessions"

    id = db.Column(db.String(36), primary_key=True, default=gen_uuid)
    faculty_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    class_section = db.Column(db.String(100), nullable=False)

    latitude = db.Column(db.Float, nullable=False)   # faculty's location when QR was generated
    longitude = db.Column(db.Float, nullable=False)
    radius_meters = db.Column(db.Float, default=50)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)  # lecture window closes
    is_active = db.Column(db.Boolean, default=True)

    faculty = db.relationship("User", foreign_keys=[faculty_id])


class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey("lecture_sessions.id"), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    scanned_at = db.Column(db.DateTime, default=datetime.utcnow)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    distance_meters = db.Column(db.Float)
    status = db.Column(db.String(20), default="present")
    selfie_photo = db.Column(db.String(255), nullable=True)
    face_match_score = db.Column(db.Float, nullable=True)

    __table_args__ = (db.UniqueConstraint("session_id", "student_id", name="uq_session_student"),)

    session = db.relationship("LectureSession", foreign_keys=[session_id])
    student = db.relationship("User", foreign_keys=[student_id])


class Marks(db.Model):
    __tablename__ = "marks"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    faculty_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)
    student_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    subject = db.Column(db.String(150), nullable=False)
    exam_type = db.Column(db.String(50), nullable=False)  # e.g. Midterm, Final, Quiz1
    marks_obtained = db.Column(db.Float, nullable=False)
    max_marks = db.Column(db.Float, nullable=False)

    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("User", foreign_keys=[student_id])
