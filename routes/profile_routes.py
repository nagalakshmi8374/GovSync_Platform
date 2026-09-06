from flask import Blueprint, render_template, request, session
from config.database import get_db_connection
from utils.auth import login_required
from utils.password import hash_password, verify_password

profile_bp = Blueprint("profile", __name__)

DEFAULT_SETTINGS = {
    "theme": "light",
    "notify_syllabus_updates": True,
    "notify_exam_reminders": True,
    "notify_preparation_reminders": False,
    "notify_recommended_exams": True,
    "exam_category": "all",
    "language": "english",
    "update_frequency": "important",
}
BOOLEAN_KEYS = {"notify_syllabus_updates", "notify_exam_reminders", "notify_preparation_reminders", "notify_recommended_exams"}
STRING_KEYS = {"theme", "exam_category", "language", "update_frequency"}
ALL_KEYS = BOOLEAN_KEYS | STRING_KEYS

@profile_bp.route("/settings")
@login_required
def settings():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT full_name, email, phone_number, preparation_type FROM users WHERE id = %s", (session["user_id"],))
            profile = cur.fetchone()
            cur.execute("SELECT theme, notify_syllabus_updates, notify_exam_reminders, notify_preparation_reminders, notify_recommended_exams, exam_category, language, update_frequency FROM user_settings WHERE user_id = %s", (session["user_id"],))
            settings_row = cur.fetchone()
            if not settings_row:
                cur.execute("INSERT INTO user_settings (user_id) VALUES (%s) RETURNING theme, notify_syllabus_updates, notify_exam_reminders, notify_preparation_reminders, notify_recommended_exams, exam_category, language, update_frequency", (session["user_id"],))
                settings_row = cur.fetchone()
            conn.commit()
            return render_template("settings.html", profile=profile, settings=dict(settings_row))
    finally:
        conn.close()

@profile_bp.route("/api/update-profile", methods=["POST"])
@login_required
def update_profile():
    data = request.get_json() or {}
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone_number") or "").strip()
    preparation_type = (data.get("preparation_type") or "Multiple Exams").strip()
    if not full_name or not email:
        return {"success": False, "message": "Name and email are required."}, 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE LOWER(email) = %s AND id <> %s", (email, session["user_id"]))
            if cur.fetchone():
                return {"success": False, "message": "That email is already in use."}, 409
            cur.execute(
                """UPDATE users SET full_name=%s, email=%s, phone_number=%s, preparation_type=%s
                   WHERE id=%s""",
                (full_name, email, phone, preparation_type, session["user_id"])
            )
        conn.commit()
        session["user_name"] = full_name
        session["user_email"] = email
        return {"success": True, "full_name": full_name, "email": email, "phone_number": phone, "preparation_type": preparation_type}
    except Exception as exc:
        conn.rollback()
        print("PROFILE UPDATE ERROR:", repr(exc))
        return {"success": False, "message": "Could not update profile."}, 500
    finally:
        conn.close()

@profile_bp.route("/api/update-password", methods=["POST"])
@login_required
def update_password():
    data = request.get_json() or {}
    current = data.get("current_password", "")
    new = data.get("new_password", "")
    confirm = data.get("confirm_password", "")
    if not current or not new or not confirm:
        return {"success": False, "message": "Please fill in all password fields."}, 400
    if new != confirm:
        return {"success": False, "message": "New passwords do not match."}, 400
    if len(new) < 8:
        return {"success": False, "message": "New password must contain at least 8 characters."}, 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash, password FROM users WHERE id=%s", (session["user_id"],))
            user = cur.fetchone()
            stored = user["password_hash"] or user["password"]
            if not stored or not verify_password(stored, current):
                return {"success": False, "message": "Current password is incorrect."}, 400
            cur.execute("UPDATE users SET password_hash=%s, password=NULL WHERE id=%s", (hash_password(new), session["user_id"]))
        conn.commit()
        return {"success": True, "message": "Password updated successfully."}
    except Exception as exc:
        conn.rollback()
        print("PASSWORD UPDATE ERROR:", repr(exc))
        return {"success": False, "message": "Could not update password."}, 500
    finally:
        conn.close()

@profile_bp.route("/api/update-setting", methods=["POST"])
@login_required
def update_setting():
    data = request.get_json() or {}
    key, value = data.get("key"), data.get("value")
    if key not in ALL_KEYS:
        return {"success": False, "message": "Invalid setting."}, 400
    if key in BOOLEAN_KEYS:
        value = bool(value)
    else:
        value = str(value).strip()

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO user_settings (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (session["user_id"],))
            cur.execute(f"UPDATE user_settings SET {key}=%s, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s", (value, session["user_id"]))
        conn.commit()
        return {"success": True}
    except Exception as exc:
        conn.rollback()
        print("SETTING UPDATE ERROR:", repr(exc))
        return {"success": False, "message": "Could not save this setting."}, 500
    finally:
        conn.close()
