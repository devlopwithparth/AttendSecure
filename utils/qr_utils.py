import io
import base64
import qrcode
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="qr-attendance-token")


def make_qr_token(session_id):
    """Creates a signed token embedding the lecture session id.
    The token itself is time-limited (QR_TOKEN_VALID_SECONDS) so a screenshot
    shared outside class becomes useless within seconds — this stacks on top
    of the GPS geofence check done at scan time."""
    return _serializer().dumps({"session_id": session_id})


def verify_qr_token(token):
    """Returns (session_id, error_message). session_id is None on failure."""
    max_age = current_app.config["QR_TOKEN_VALID_SECONDS"]
    try:
        data = _serializer().loads(token, max_age=max_age)
        return data.get("session_id"), None
    except SignatureExpired:
        return None, "This QR code has expired — ask faculty for the current one."
    except BadSignature:
        return None, "Invalid QR code."


def qr_token_to_image_base64(token):
    """Renders a token string as a QR PNG, returned as a base64 data-URI for inline <img> use."""
    img = qrcode.make(token)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"
