# AttendSecure — OTP Login & Geofenced QR Attendance System

MSc Cybersecurity final project scaffold: two portals (Faculty / Student), registered-email OTP
two-factor login, selfie verification, and GPS-geofenced, rotating-token QR attendance.

## 1. Setup

```bash
cd attendance_system
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file (or just set env vars) if you want real email OTPs:

```
SECRET_KEY=change-this-to-something-long-and-random
OTP_DEV_MODE=false
MAIL_USERNAME=your_gmail@gmail.com
MAIL_PASSWORD=your_gmail_app_password   # use a Gmail "App Password", not your real password
MAIL_DEFAULT_SENDER=your_gmail@gmail.com
```

By default `OTP_DEV_MODE=true`, which **prints the OTP to the console** instead of emailing it —
useful while developing so you don't need SMTP credentials set up yet.

## 2. Run

```bash
python app.py
```

Visit `http://localhost:5000`. Use `http://<your-lan-ip>:5000` from a phone on the same network
to test camera + GPS scanning on a real device (browsers generally require HTTPS or `localhost`
for camera/geolocation — see note below).

## 3. Try it end-to-end

1. Sign up as **faculty** → verify OTP (check console if `OTP_DEV_MODE=true`) → log in (password + OTP).
2. On the faculty dashboard, click **"Capture my current location"**, fill in subject/class, **Generate QR & start**.
3. In another browser (or incognito) sign up as **student** → verify → log in.
4. Go to **Scan QR**, take the required selfie, allow camera + location, scan the QR shown on the faculty screen.
5. Attendance should appear instantly on the faculty's live session page; check the student's
   **Attendance** tab too. Try exporting Excel/PDF from both sides.

## 4. Security design notes (useful for your report)

- **Password storage**: bcrypt via Flask-Bcrypt, salted hashes only — plaintext never stored.
- **OTP**: 6-digit, itself hashed at rest (not stored plain), 5-minute expiry, max 3 attempts,
  automatically invalidated on a new request (no stale multi-OTP validity window), resend cooldown.
- **Selfie gate before QR scan**: student signup requires a registration photo. Before QR scanning,
  the student must take a live selfie; the server compares it with the registration photo and only
  unlocks QR scanning after a match.
- **2FA on every login**: password success alone does not create a session — a fresh OTP is
  required each time, closing the "stolen password only" gap.
- **Device-awareness without hard-locking**: rather than blocking new devices outright (which
  breaks usability if a student's phone dies), every successful login writes an audit row
  (`LoginLog`: IP, user-agent, fingerprint, timestamp). This is where you could add anomaly
  detection (e.g., flag/alert on logins from a device+location combo never seen before) as a
  stretch goal / discussion point in your dissertation.
- **QR attendance — two independent controls stacked**:
  1. **Geofencing**: server computes Haversine distance between the student's reported GPS and
     the faculty's GPS at QR-generation time; scan is rejected outside `radius_meters`.
  2. **Rotating signed token**: the QR image itself encodes a token signed with the app's
     `SECRET_KEY` (`itsdangerous`) that expires in `QR_TOKEN_VALID_SECONDS` (default 25s) and
     auto-refreshes on the faculty's screen. This defeats "photograph the QR and send it to a
     friend at home" — by the time it arrives, it's expired, *and* the friend's GPS still fails
     the geofence check even if it hadn't.
- **Replay protection**: a unique constraint on `(session_id, student_id)` stops double-scanning.
- **Authorization**: `role_required` decorator enforces faculty/student separation on every route;
  faculty can only view/export/close their *own* sessions (checked via `faculty_id` ownership,
  not just role).

## 5. Known limitations / good "future work" items for your report

- GPS can be spoofed by rooted/jailbroken devices or browser dev tools — worth discussing as a
  threat model limitation, and mentioning mitigations (e.g., cross-checking WiFi BSSID as a
  second factor, or mock-location detection on native apps) as future work.
- No refresh-token/JWT-based API separation yet — sessions use Flask's signed cookie, fine for a
  monolith but would need adapting for a separate mobile app.
- Rate limiting is only implemented for OTP attempts, not for login attempts generally — consider
  adding Flask-Limiter for brute-force protection on `/auth/login` for full marks.
- No HTTPS in the dev server — camera/geolocation APIs require a "secure context" (HTTPS or
  localhost) in real browsers, so for LAN device testing you'll need a tool like `ngrok` or a
  self-signed cert; for your final deployment, run behind HTTPS.

## 6. Project structure

```
attendance_system/
├── app.py                  # Flask app factory
├── config.py                # Settings: OTP, geofence radius, QR token TTL, mail
├── extensions.py             # Shared db/bcrypt/mail instances
├── models.py                 # User, OTP, LoginLog, LectureSession, Attendance, Marks
├── auth/routes.py            # Signup, login, OTP verify/resend (both roles)
├── faculty/routes.py         # Start/close session, live QR + attendance, marks upload, exports
├── student/routes.py         # Scan submit, attendance analysis, marks view, exports
├── utils/
│   ├── otp_utils.py           # Generate/hash/verify/send OTP
│   ├── geo_utils.py           # Haversine distance / radius check
│   ├── qr_utils.py            # Signed rotating QR tokens + image rendering
│   ├── export_utils.py        # Excel (openpyxl) + PDF (reportlab) builders
│   └── auth_utils.py          # login_required / role_required decorators
├── templates/                # Jinja2 templates (auth, faculty, student, base shell)
└── static/css/style.css      # Shared stylesheet
```
