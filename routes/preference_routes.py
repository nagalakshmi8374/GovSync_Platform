from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from config.database import get_db_connection
from utils.auth import login_required

preferences_bp = Blueprint("preferences", __name__)

@preferences_bp.route("/preference", methods=["GET", "POST"])
@login_required
def preference():
    user_id = session["user_id"]
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            if request.method == "POST":
                selected_exams = [e.strip().upper() for e in request.form.getlist("exams") if e.strip()]
                if not selected_exams:
                    flash("Please select at least one exam.", "error")
                    return redirect(url_for("preferences.preference"))

                for exam in selected_exams:
                    cur.execute(
                        """INSERT INTO user_exams (user_id, exam_code)
                           VALUES (%s, %s)
                           ON CONFLICT (user_id, exam_code) DO NOTHING""",
                        (user_id, exam)
                    )
                cur.execute("UPDATE users SET preferences_completed = TRUE WHERE id = %s", (user_id,))
                conn.commit()
                return redirect(url_for("dashboard.dashboard"))

            cur.execute("SELECT exam_code FROM user_exams WHERE user_id = %s ORDER BY id", (user_id,))
            selected = [r["exam_code"] for r in cur.fetchall()]
            cur.execute("SELECT preferences_completed FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if user and user["preferences_completed"]:
                return redirect(url_for("dashboard.dashboard"))
            return render_template("preference.html", selected_exams=selected)
    except Exception as exc:
        if conn:
            conn.rollback()
        print("PREFERENCE ERROR:", repr(exc))
        flash("Unable to save preferences.", "error")
        return redirect(url_for("dashboard.dashboard"))
    finally:
        if conn:
            conn.close()

@preferences_bp.route("/api/preferences/status")
@login_required
def preference_status():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT preferences_completed FROM users WHERE id = %s", (session["user_id"],))
            row = cur.fetchone()
            return {"success": True, "preferences_completed": bool(row and row["preferences_completed"])}
    finally:
        conn.close()
