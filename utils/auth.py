from functools import wraps
from flask import session, redirect, url_for, flash, jsonify
from config.config import Config

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request_wants_json():
                return jsonify({"success": False, "message": "Please login first."}), 401
            flash("Please login first.", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped

def request_wants_json():
    from flask import request
    return request.is_json or request.path.startswith("/api/")

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("auth.login"))
        if not session.get("is_admin"):
            if request_wants_json():
                return jsonify({"success": False, "message": "Administrator access required."}), 403
            flash("Administrator access required.", "error")
            return redirect(url_for("dashboard.dashboard"))
        return view(*args, **kwargs)
    return wrapped

def is_admin_user(user):
    return user.get("role") == "admin" or user.get("email", "").lower() in Config.ADMIN_EMAILS
