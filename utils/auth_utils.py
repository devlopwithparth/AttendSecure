from functools import wraps
from flask import session, redirect, url_for, flash, request


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "error")
                return redirect(url_for("auth.login"))
            if session.get("role") != role:
                flash("You are not authorized to view that page.", "error")
                return redirect(url_for("auth.login"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def get_client_fingerprint():
    """A lightweight device fingerprint from request headers.
    Not cryptographically unique, but useful for anomaly logging (new device alerts)."""
    ua = request.headers.get("User-Agent", "")
    accept_lang = request.headers.get("Accept-Language", "")
    return f"{ua}|{accept_lang}"
