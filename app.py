import os
from flask import Flask, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

from config import Config
from extensions import db, bcrypt, mail


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ensure instance folder exists (for SQLite file)
    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "uploads", "student_photos"), exist_ok=True)
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "uploads", "selfies"), exist_ok=True)

    db.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)

    from auth.routes import auth_bp
    from faculty.routes import faculty_bp
    from student.routes import student_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(faculty_bp, url_prefix="/faculty")
    app.register_blueprint(student_bp, url_prefix="/student")

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    with app.app_context():
        db.create_all()
        _ensure_sqlite_columns()

    return app


def _ensure_sqlite_columns():
    if db.engine.dialect.name != "sqlite":
        return

    user_columns = {
        row[1]
        for row in db.session.execute(db.text("PRAGMA table_info(users)")).fetchall()
    }
    if "profile_photo" not in user_columns:
        db.session.execute(db.text("ALTER TABLE users ADD COLUMN profile_photo VARCHAR(255)"))

    attendance_columns = {
        row[1]
        for row in db.session.execute(db.text("PRAGMA table_info(attendance)")).fetchall()
    }
    if "selfie_photo" not in attendance_columns:
        db.session.execute(db.text("ALTER TABLE attendance ADD COLUMN selfie_photo VARCHAR(255)"))
    if "face_match_score" not in attendance_columns:
        db.session.execute(db.text("ALTER TABLE attendance ADD COLUMN face_match_score FLOAT"))

    db.session.commit()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
