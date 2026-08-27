import psycopg
from flask import Flask, render_template, request, redirect, url_for, session, flash
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)

# ============================================================
# EXAM DISPLAY NAMES (shared across routes)
# ============================================================

EXAM_NAMES = {
    "UPSC": "UPSC Civil Services",
    "SSC": "SSC CGL",
    "IBPS": "IBPS PO",
    "RRB": "RRB NTPC",
    "GATE": "GATE",
    "ESE": "Engineering Services",
    "PSC": "State PSC",
    "DEFENCE": "Defence Exams"
}


# ============================================================
# PROFILE + SETTINGS HELPERS
#
# Expects the users table to be extended with:
#
#   ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20);
#   ALTER TABLE users ADD COLUMN IF NOT EXISTS preparation_type VARCHAR(50)
#       NOT NULL DEFAULT 'Multiple Exams';
#
# And a new table for per-user settings (theme, notification
# toggles, preferences):
#
#   CREATE TABLE IF NOT EXISTS user_settings (
#       user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
#       theme VARCHAR(10) NOT NULL DEFAULT 'light',
#       notify_syllabus_updates BOOLEAN NOT NULL DEFAULT TRUE,
#       notify_exam_reminders BOOLEAN NOT NULL DEFAULT TRUE,
#       notify_preparation_reminders BOOLEAN NOT NULL DEFAULT FALSE,
#       notify_recommended_exams BOOLEAN NOT NULL DEFAULT TRUE,
#       exam_category VARCHAR(50) NOT NULL DEFAULT 'all',
#       language VARCHAR(20) NOT NULL DEFAULT 'english',
#       update_frequency VARCHAR(20) NOT NULL DEFAULT 'important',
#       updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
#   );
# ============================================================

DEFAULT_USER_SETTINGS = {
    "theme": "light",
    "notify_syllabus_updates": True,
    "notify_exam_reminders": True,
    "notify_preparation_reminders": False,
    "notify_recommended_exams": True,
    "exam_category": "all",
    "language": "english",
    "update_frequency": "important"
}

BOOLEAN_SETTING_KEYS = {
    "notify_syllabus_updates",
    "notify_exam_reminders",
    "notify_preparation_reminders",
    "notify_recommended_exams"
}

STRING_SETTING_KEYS = {
    "theme",
    "exam_category",
    "language",
    "update_frequency"
}

ALL_SETTING_KEYS = BOOLEAN_SETTING_KEYS | STRING_SETTING_KEYS


def get_user_profile(cur, user_id, fallback_name="User", fallback_email=""):
    """Fetch a user's editable profile fields."""

    cur.execute(
        """
        SELECT full_name, email, phone_number, preparation_type
        FROM users
        WHERE id = %s
        """,
        (user_id,)
    )

    row = cur.fetchone()

    if not row:
        return {
            "full_name": fallback_name,
            "email": fallback_email,
            "phone_number": "",
            "preparation_type": "Multiple Exams"
        }

    return {
        "full_name": row["full_name"],
        "email": row["email"],
        "phone_number": row["phone_number"] or "",
        "preparation_type": row["preparation_type"] or "Multiple Exams"
    }


def get_or_create_user_settings(cur, user_id):
    """Fetch a user's settings row, creating a default one if missing."""

    cur.execute(
        """
        SELECT theme, notify_syllabus_updates, notify_exam_reminders,
               notify_preparation_reminders, notify_recommended_exams,
               exam_category, language, update_frequency
        FROM user_settings
        WHERE user_id = %s
        """,
        (user_id,)
    )

    row = cur.fetchone()

    if row:
        return dict(row)

    cur.execute(
        """
        INSERT INTO user_settings (user_id)
        VALUES (%s)
        RETURNING theme, notify_syllabus_updates, notify_exam_reminders,
                  notify_preparation_reminders, notify_recommended_exams,
                  exam_category, language, update_frequency
        """,
        (user_id,)
    )

    return dict(cur.fetchone())


# ============================================================
# SYLLABUS UPDATES HELPERS
#
# Expects a table created something like:
#
#   CREATE TABLE syllabus_updates (
#       id SERIAL PRIMARY KEY,
#       exam_code VARCHAR(20),          -- NULL = general update (all exams)
#       title VARCHAR(255) NOT NULL,
#       description TEXT,
#       updated_section VARCHAR(150),
#       change_type VARCHAR(100),
#       posted_by INTEGER REFERENCES users(id),
#       created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
#   );
#
# Admins insert rows with a specific exam_code (exam-specific
# update) or with exam_code = NULL (a general update that should
# be shown to every user, regardless of which exams they picked).
# ============================================================

def time_ago(dt):
    """Turn a datetime into a short human readable string."""

    if dt is None:
        return ""

    diff = datetime.now() - dt
    days = diff.days

    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"

    months = days // 30
    return f"{months} month{'s' if months > 1 else ''} ago"


def get_user_exam_codes(cur, user_id):
    """Return the list of exam codes the user has selected."""

    cur.execute(
        """
        SELECT exam_code
        FROM user_exams
        WHERE user_id = %s
        ORDER BY id
        """,
        (user_id,)
    )

    return [str(row["exam_code"]).upper() for row in cur.fetchall()]


def fetch_updates_for_user(cur, exam_codes, limit=None):
    """
    Return syllabus updates relevant to this user: updates tied
    to one of their selected exams, plus general (admin, exam_code
    IS NULL) updates that apply to everyone.
    """

    if not exam_codes:
        # Still show general/admin updates even if user picked no exams
        query = """
            SELECT id, exam_code, title, description,
                   updated_section, change_type, created_at
            FROM syllabus_updates
            WHERE exam_code IS NULL
            ORDER BY created_at DESC
        """
        params = ()
    else:
        query = """
            SELECT id, exam_code, title, description,
                   updated_section, change_type, created_at
            FROM syllabus_updates
            WHERE exam_code IS NULL
               OR UPPER(exam_code) = ANY(%s)
            ORDER BY created_at DESC
        """
        params = (exam_codes,)

    if limit:
        query += " LIMIT %s"
        params = params + (limit,)

    cur.execute(query, params)
    rows = cur.fetchall()

    updates = []

    for row in rows:

        code = row["exam_code"]
        code = str(code).upper() if code else None

        updates.append({
            "id": row["id"],
            "exam_code": code,
            "exam_name": EXAM_NAMES.get(code, code) if code else "All Exams",
            "title": row["title"],
            "description": row["description"],
            "updated_section": row["updated_section"],
            "change_type": row["change_type"],
            "created_at": row["created_at"],
            "time_text": time_ago(row["created_at"]),
            "is_new": (
                row["created_at"] is not None
                and (datetime.now() - row["created_at"]).days < 7
            )
        })

    return updates

# Secret key for Flask sessions and flash messages
app.secret_key = "govsync-secret-key-change-this"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():
    return psycopg.connect(
        host="localhost",
        port="5432",
        dbname="govsync",
        user="postgres",
        password="password",
        row_factory=dict_row
    )


# ============================================================
# LOGIN + REGISTER PAGE
# ============================================================

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/progress")
def progress():

    if "user_id" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    conn = None
    exams = []
    overall_progress = 0
    total_completed = 0
    total_topics_all = 0
    recent_activity = []

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            # Same per-exam progress calculation used on the dashboard
            cur.execute(
                """
                SELECT
                    ue.id AS user_exam_id,
                    ue.exam_code,
                    COUNT(t.id) AS total_topics,
                    COUNT(p.topic_id) FILTER (WHERE p.completed = TRUE) AS completed_topics
                FROM user_exams ue
                CROSS JOIN topics t
                JOIN subjects s
                    ON s.id = t.subject_id
                    AND UPPER(s.subject_code) IN
                        ('REASONING', 'QUANT', 'ENGLISH', 'AWARENESS')
                LEFT JOIN user_topic_progress p
                    ON p.topic_id = t.id
                    AND p.user_exam_id = ue.id
                WHERE ue.user_id = %s
                GROUP BY ue.id, ue.exam_code
                ORDER BY ue.id
                """,
                (session["user_id"],)
            )

            rows = cur.fetchall()

            for row in rows:

                total_topics = row["total_topics"] or 0
                completed_topics = row["completed_topics"] or 0

                exam_progress = (
                    round((completed_topics / total_topics) * 100)
                    if total_topics else 0
                )

                code = str(row["exam_code"]).upper()

                if exam_progress == 0:
                    status = "Getting Started"
                elif exam_progress >= 100:
                    status = "Completed"
                else:
                    status = "In Progress"

                exams.append({
                    "exam_code": code,
                    "exam_name": EXAM_NAMES.get(code, code),
                    "progress": exam_progress,
                    "completed_topics": completed_topics,
                    "total_topics": total_topics,
                    "status": status
                })

                total_completed += completed_topics
                total_topics_all += total_topics

            overall_progress = (
                round((total_completed / total_topics_all) * 100)
                if total_topics_all else 0
            )

            # ================================================
            # RECENT ACTIVITY (last topics marked complete)
            # ================================================

            cur.execute(
                """
                SELECT
                    ue.exam_code,
                    t.topic_name,
                    p.completed_at
                FROM user_topic_progress p
                JOIN user_exams ue
                    ON ue.id = p.user_exam_id
                JOIN topics t
                    ON t.id = p.topic_id
                WHERE ue.user_id = %s
                  AND p.completed = TRUE
                ORDER BY p.completed_at DESC
                LIMIT 5
                """,
                (session["user_id"],)
            )

            for row in cur.fetchall():

                code = str(row["exam_code"]).upper()

                recent_activity.append({
                    "exam_name": EXAM_NAMES.get(code, code),
                    "topic_name": row["topic_name"],
                    "time_text": time_ago(row["completed_at"])
                })

    except Exception as e:

        print("PROGRESS ERROR:", e)

    finally:

        if conn:
            conn.close()

    return render_template(
        "progress.html",
        exams=exams,
        exam_count=len(exams),
        overall_progress=overall_progress,
        topics_completed=total_completed,
        topics_remaining_pct=100 - overall_progress,
        recent_activity=recent_activity,
        user_name=session.get("user_name", "User")
    )


@app.route("/updates")
def updates():

    if "user_id" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    conn = None
    all_updates = []
    exam_codes = []

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            exam_codes = get_user_exam_codes(cur, session["user_id"])
            all_updates = fetch_updates_for_user(cur, exam_codes)

    except Exception as e:

        print("UPDATES ERROR:", e)

    finally:

        if conn:
            conn.close()

    total_updates = len(all_updates)
    new_updates = sum(1 for u in all_updates if u["is_new"])
    exams_updated = len({
        u["exam_code"] for u in all_updates if u["exam_code"]
    })

    filter_exams = [
        {"code": code, "name": EXAM_NAMES.get(code, code)}
        for code in exam_codes
    ]

    return render_template(
        "updates.html",
        updates=all_updates,
        total_updates=total_updates,
        new_updates=new_updates,
        exams_updated=exams_updated,
        filter_exams=filter_exams,
        user_name=session.get("user_name", "User")
    )


@app.route("/settings")
def settings():

    if "user_id" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    conn = None
    profile = {
        "full_name": session.get("user_name", "User"),
        "email": session.get("user_email", ""),
        "phone_number": "",
        "preparation_type": "Multiple Exams"
    }
    user_settings = DEFAULT_USER_SETTINGS.copy()

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            profile = get_user_profile(
                cur,
                session["user_id"],
                session.get("user_name", "User"),
                session.get("user_email", "")
            )

            user_settings = get_or_create_user_settings(cur, session["user_id"])

        conn.commit()

    except Exception as e:

        if conn:
            conn.rollback()

        print("SETTINGS LOAD ERROR:", e)

    finally:

        if conn:
            conn.close()

    return render_template(
        "settings.html",
        profile=profile,
        settings=user_settings
    )


# ============================================================
# PROFILE / PASSWORD / SETTINGS APIs
# ============================================================

@app.route("/api/update-profile", methods=["POST"])
def update_profile():

    if "user_id" not in session:
        return {"success": False, "message": "Please login first."}, 401

    data = request.get_json() or {}

    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    phone_number = (data.get("phone_number") or "").strip()
    preparation_type = (data.get("preparation_type") or "Multiple Exams").strip()

    if not full_name or not email:
        return {
            "success": False,
            "message": "Name and email are required."
        }, 400

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            cur.execute(
                """
                UPDATE users
                SET full_name = %s,
                    email = %s,
                    phone_number = %s,
                    preparation_type = %s
                WHERE id = %s
                """,
                (
                    full_name,
                    email,
                    phone_number,
                    preparation_type,
                    session["user_id"]
                )
            )

        conn.commit()

        # Keep the session in sync so header/menu names update immediately
        session["user_name"] = full_name
        session["user_email"] = email

        return {
            "success": True,
            "full_name": full_name,
            "email": email,
            "phone_number": phone_number,
            "preparation_type": preparation_type
        }

    except Exception as e:

        if conn:
            conn.rollback()

        print("PROFILE UPDATE ERROR:", e)

        return {
            "success": False,
            "message": "Could not update profile. That email may already be in use."
        }, 500

    finally:

        if conn:
            conn.close()


@app.route("/api/update-password", methods=["POST"])
def update_password():

    if "user_id" not in session:
        return {"success": False, "message": "Please login first."}, 401

    data = request.get_json() or {}

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    if not current_password or not new_password or not confirm_password:
        return {
            "success": False,
            "message": "Please fill in all password fields."
        }, 400

    if new_password != confirm_password:
        return {
            "success": False,
            "message": "New passwords do not match."
        }, 400

    if len(new_password) < 6:
        return {
            "success": False,
            "message": "New password must contain at least 6 characters."
        }, 400

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            cur.execute(
                "SELECT password_hash FROM users WHERE id = %s",
                (session["user_id"],)
            )

            user = cur.fetchone()

            if not user or not check_password_hash(
                user["password_hash"], current_password
            ):
                return {
                    "success": False,
                    "message": "Current password is incorrect."
                }, 400

            new_hash = generate_password_hash(new_password)

            cur.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (new_hash, session["user_id"])
            )

        conn.commit()

        return {
            "success": True,
            "message": "Password updated successfully."
        }

    except Exception as e:

        if conn:
            conn.rollback()

        print("PASSWORD UPDATE ERROR:", e)

        return {
            "success": False,
            "message": "Could not update password."
        }, 500

    finally:

        if conn:
            conn.close()


@app.route("/api/update-setting", methods=["POST"])
def update_setting():

    if "user_id" not in session:
        return {"success": False, "message": "Please login first."}, 401

    data = request.get_json() or {}

    key = data.get("key")
    value = data.get("value")

    if key not in ALL_SETTING_KEYS:
        return {"success": False, "message": "Invalid setting."}, 400

    if key in BOOLEAN_SETTING_KEYS:
        value = bool(value)
    else:
        value = str(value).strip()

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            # Make sure a settings row exists before updating it
            get_or_create_user_settings(cur, session["user_id"])

            cur.execute(
                f"""
                UPDATE user_settings
                SET {key} = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                """,
                (value, session["user_id"])
            )

        conn.commit()

        return {"success": True}

    except Exception as e:

        if conn:
            conn.rollback()

        print("SETTING UPDATE ERROR:", e)

        return {
            "success": False,
            "message": "Could not save this setting."
        }, 500

    finally:

        if conn:
            conn.close()


@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Check empty fields
        if not email or not password:
            flash("Please enter your email and password.", "error")
            return redirect(url_for("login"))

        conn = None

        try:
            conn = get_db_connection()

            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT id, full_name, email, password_hash
                    FROM users
                    WHERE email = %s
                    """,
                    (email,)
                )

                user = cur.fetchone()

            # User doesn't exist
            if user is None:
                flash("Invalid email or password.", "error")
                return redirect(url_for("login"))

            # Check password
            if not check_password_hash(user["password_hash"], password):
                flash("Invalid email or password.", "error")
                return redirect(url_for("login"))

            # Login successful
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            session["user_email"] = user["email"]

            flash("Login successful!", "success")
            

            # For now redirect to dashboard
            # Change this later when your dashboard is ready.
            return redirect(url_for("preference"))

        except Exception as e:

            print("LOGIN ERROR:", e)

            flash("Something went wrong while logging in.", "error")

            return redirect(url_for("login"))

        finally:

            if conn:
                conn.close()

    return render_template("login.html")


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["POST"])
def register():

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    # Check empty fields
    if not full_name or not email or not password or not confirm_password:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("login"))

    # Check password match
    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("login"))

    # Check password length
    if len(password) < 6:
        flash("Password must contain at least 6 characters.", "error")
        return redirect(url_for("login"))

    # Generate secure password hash
    password_hash = generate_password_hash(password)

    conn = None

    try:

        conn = get_db_connection()

        with conn.cursor() as cur:

            # Check whether email already exists
            cur.execute(
                """
                SELECT id
                FROM users
                WHERE email = %s
                """,
                (email,)
            )

            existing_user = cur.fetchone()

            if existing_user:
                flash("An account with this email already exists.", "error")
                return redirect(url_for("login"))

            # Insert new user
            cur.execute(
                """
                INSERT INTO users
                    (full_name, email, password_hash)
                VALUES
                    (%s, %s, %s)
                """,
                (full_name, email, password_hash)
            )

        conn.commit()

        flash("Account created successfully. Please sign in.", "success")

        return redirect(url_for("login"))

    except Exception as e:

        if conn:
            conn.rollback()

        print("REGISTER ERROR:", e)

        flash("Something went wrong while creating your account.", "error")

        return redirect(url_for("login"))

    finally:

        if conn:
            conn.close()


# ============================================================
# DASHBOARD
# ===========================================================
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    today = datetime.now()

    exam_names = {
        "UPSC": "UPSC Civil Services",
        "SSC": "SSC CGL",
        "IBPS": "IBPS PO",
        "RRB": "RRB NTPC",
        "GATE": "GATE",
        "ESE": "Engineering Services",
        "PSC": "State PSC",
        "DEFENCE": "Defence Exams"
    }

    conn = None
    exams = []
    overall_progress = 0
    total_completed = 0
    recent_updates = []
    updates_count = 0
    profile = {
        "full_name": session.get("user_name", "User"),
        "email": session.get("user_email", ""),
        "phone_number": "",
        "preparation_type": "Multiple Exams"
    }

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            # ================================================
            # For every exam the user selected, count how many
            # of the 4 common-subject topics are marked
            # completed for THAT exam specifically.
            # ================================================

            cur.execute(
                """
                SELECT
                    ue.id AS user_exam_id,
                    ue.exam_code,
                    COUNT(t.id) AS total_topics,
                    COUNT(p.topic_id) FILTER (WHERE p.completed = TRUE) AS completed_topics
                FROM user_exams ue
                CROSS JOIN topics t
                JOIN subjects s
                    ON s.id = t.subject_id
                    AND UPPER(s.subject_code) IN
                        ('REASONING', 'QUANT', 'ENGLISH', 'AWARENESS')
                LEFT JOIN user_topic_progress p
                    ON p.topic_id = t.id
                    AND p.user_exam_id = ue.id
                WHERE ue.user_id = %s
                GROUP BY ue.id, ue.exam_code
                ORDER BY ue.id
                """,
                (session["user_id"],)
            )

            rows = cur.fetchall()

        total_topics_all = 0

        for row in rows:

            total_topics = row["total_topics"] or 0
            completed_topics = row["completed_topics"] or 0

            progress = (
                round((completed_topics / total_topics) * 100)
                if total_topics else 0
            )

            code = str(row["exam_code"]).upper()

            exams.append({
                "exam_code": code,
                "exam_name": exam_names.get(code, code),
                "progress": progress,
                "completed_topics": completed_topics,
                "total_topics": total_topics
            })

            total_completed += completed_topics
            total_topics_all += total_topics

        overall_progress = (
            round((total_completed / total_topics_all) * 100)
            if total_topics_all else 0
        )

        # ================================================
        # RECENTLY SYLLABUS UPDATES
        # (user's selected exams + general admin updates)
        # ================================================

        with conn.cursor() as cur:

            exam_codes = get_user_exam_codes(cur, session["user_id"])
            all_updates = fetch_updates_for_user(cur, exam_codes)

        updates_count = len(all_updates)
        recent_updates = all_updates[:3]

        # ================================================
        # PROFILE (for the profile edit panel)
        # ================================================

        with conn.cursor() as cur:
            profile = get_user_profile(
                cur,
                session["user_id"],
                session.get("user_name", "User"),
                session.get("user_email", "")
            )

    except Exception as e:

        print("DASHBOARD ERROR:", e)

    finally:

        if conn:
            conn.close()

    return render_template(
        "dashboard.html",
        today=today,
        exams=exams,
        exam_count=len(exams),
        overall_progress=overall_progress,
        topics_completed=total_completed,
        recent_updates=recent_updates,
        updates_count=updates_count,
        profile=profile
    )


@app.route("/myexams")
def myexams():

    if "user_id" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    conn = None
    exams = []

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            # Get selected exams
            cur.execute(
                """
                SELECT exam_code
                FROM user_exams
                WHERE user_id = %s
                ORDER BY id
                """,
                (session["user_id"],)
            )

            rows = cur.fetchall()

            exams = [
                row["exam_code"]
                for row in rows
            ]

    except Exception as e:

        print("MY EXAMS ERROR:", e)

    finally:

        if conn:
            conn.close()

    return render_template(
        "my_exams.html",
        exams=exams,
        user_name=session.get("user_name", "User"),
        user_email=session.get("user_email", "")
    )



@app.route("/preference", methods=["GET", "POST"])
def preference():

    if "user_id" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # =====================================
    # SAVE SELECTED EXAMS
    # =====================================

    if request.method == "POST":

        selected_exams = request.form.getlist("exams")

        if not selected_exams:
            flash("Please select at least one exam.", "error")
            return redirect(url_for("preference"))

        conn = None

        try:

            conn = get_db_connection()

            with conn.cursor() as cur:

                for exam in selected_exams:

                    cur.execute(
                        """
                        INSERT INTO user_exams
                            (user_id, exam_code)
                        VALUES
                            (%s, %s)
                        ON CONFLICT (user_id, exam_code)
                        DO NOTHING
                        """,
                        (user_id, exam)
                    )

            conn.commit()

            flash(
                "Exam added successfully!",
                "success"
            )

            # Go to My Exams after selection
            return redirect(url_for("myexams"))

        except Exception as e:

            if conn:
                conn.rollback()

            print("PREFERENCE ERROR:", e)

            flash(
                "Unable to save exam.",
                "error"
            )

            return redirect(url_for("preference"))

        finally:

            if conn:
                conn.close()


    # =====================================
    # LOAD ALREADY SELECTED EXAMS
    # =====================================

    conn = None
    selected_exams = []

    try:

        conn = get_db_connection()

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT exam_code
                FROM user_exams
                WHERE user_id = %s
                ORDER BY id
                """,
                (user_id,)
            )

            rows = cur.fetchall()

            selected_exams = [
                row["exam_code"]
                for row in rows
            ]

    except Exception as e:

        print("PREFERENCE LOAD ERROR:", e)

    finally:

        if conn:
            conn.close()


    return render_template(
        "preference.html",
        selected_exams=selected_exams
    )




@app.route("/api/topic-progress", methods=["POST"])
def topic_progress():

    if "user_id" not in session:
        return {
            "success": False,
            "message": "Please login first."
        }, 401

    data = request.get_json()

    user_exam_id = data.get("user_exam_id")
    topic_id = data.get("topic_id")
    completed = data.get("completed")

    if not user_exam_id or not topic_id:
        return {
            "success": False,
            "message": "Missing data."
        }, 400

    conn = None

    try:

        conn = get_db_connection()

        with conn.cursor() as cur:

            # --------------------------------
            # MAKE SURE EXAM BELONGS TO USER
            # --------------------------------

            cur.execute(
                """
                SELECT id
                FROM user_exams
                WHERE id = %s
                AND user_id = %s
                """,
                (
                    user_exam_id,
                    session["user_id"]
                )
            )

            exam = cur.fetchone()

            if not exam:

                return {
                    "success": False,
                    "message": "Invalid exam."
                }, 403


            # --------------------------------
            # SAVE PROGRESS
            # --------------------------------

            cur.execute(
                """
                INSERT INTO user_topic_progress
                (
                    user_exam_id,
                    topic_id,
                    completed,
                    completed_at
                )
                VALUES (%s, %s, %s,
                    CASE
                        WHEN %s = TRUE
                        THEN CURRENT_TIMESTAMP
                        ELSE NULL
                    END
                )

                ON CONFLICT (user_exam_id, topic_id)

                DO UPDATE SET
                    completed = EXCLUDED.completed,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    user_exam_id,
                    topic_id,
                    completed,
                    completed
                )
            )

        conn.commit()

        return {
            "success": True
        }


    except Exception as e:

        if conn:
            conn.rollback()

        print("TOPIC PROGRESS ERROR:", e)

        return {
            "success": False,
            "message": "Could not save progress."
        }, 500


    finally:

        if conn:
            conn.close()
    



@app.route("/syllabus")
def syllabus():

    if "user_id" not in session:
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    conn = None

    try:
        conn = get_db_connection()

        with conn.cursor() as cur:

            # =====================================================
            # 1. GET CURRENT USER'S SELECTED EXAMS
            # =====================================================

            cur.execute(
                """
                SELECT
                    id,
                    exam_code
                FROM user_exams
                WHERE user_id = %s
                ORDER BY id
                """,
                (session["user_id"],)
            )

            user_exams = cur.fetchall()

            if not user_exams:
                flash("Please select at least one exam first.", "error")
                return redirect(url_for("preference"))


            # =====================================================
            # 2. WORK OUT WHICH EXAM IS CURRENTLY SELECTED
            #    (?exam=ssc in the URL, otherwise the first one)
            # =====================================================

            requested_code = request.args.get("exam", "").strip().upper()

            selected_exam = None
            for exam in user_exams:
                if str(exam["exam_code"]).upper() == requested_code:
                    selected_exam = exam
                    break

            if selected_exam is None:
                selected_exam = user_exams[0]

            user_exam_id = selected_exam["id"]


            # =====================================================
            # 3. GET THE FOUR COMMON SUBJECTS, THEIR TOPICS, AND
            #    THIS SPECIFIC EXAM'S PROGRESS ON EACH TOPIC
            # =====================================================

            cur.execute(
                """
                SELECT
                    s.id AS subject_id,
                    s.subject_code,
                    s.subject_name,
                    t.id AS topic_id,
                    t.topic_name,
                    COALESCE(p.completed, FALSE) AS completed
                FROM subjects AS s
                LEFT JOIN topics AS t
                    ON t.subject_id = s.id
                LEFT JOIN user_topic_progress AS p
                    ON p.topic_id = t.id
                    AND p.user_exam_id = %s
                WHERE UPPER(s.subject_code) IN
                    ('REASONING', 'QUANT', 'ENGLISH', 'AWARENESS')
                ORDER BY s.id, t.id
                """,
                (user_exam_id,)
            )

            rows = cur.fetchall()


        # =====================================================
        # 4. CREATE SUBJECT DICTIONARY
        # =====================================================

        subjects = {}

        # Always create all four subjects.
        # This prevents KeyError / missing-key problems.

        for code in ["REASONING", "QUANT", "ENGLISH", "AWARENESS"]:

            subjects[code] = {
                "id": None,
                "code": code,
                "name": "",
                "topics": [],
                "progress": 0
            }


        # =====================================================
        # 5. PUT DATABASE DATA INTO THE FOUR SUBJECTS
        # =====================================================

        for row in rows:

            subject_code = str(row["subject_code"]).upper()

            if subject_code not in subjects:
                continue

            # Store subject information
            subjects[subject_code]["id"] = row["subject_id"]
            subjects[subject_code]["name"] = row["subject_name"]

            # Add topic only if it exists
            if row["topic_id"] is not None:

                subjects[subject_code]["topics"].append({
                    "id": row["topic_id"],
                    "name": row["topic_name"],
                    "completed": row["completed"]
                })


        # =====================================================
        # 6. COMPUTE PER-SUBJECT AND OVERALL PROGRESS
        # =====================================================

        total_topics = 0
        total_completed = 0

        for code in subjects:

            topics = subjects[code]["topics"]
            completed_count = sum(1 for t in topics if t["completed"])

            subjects[code]["progress"] = (
                round((completed_count / len(topics)) * 100)
                if topics else 0
            )

            total_topics += len(topics)
            total_completed += completed_count

        overall_progress = (
            round((total_completed / total_topics) * 100)
            if total_topics else 0
        )


        # =====================================================
        # 7. EXAM DISPLAY NAMES
        # =====================================================

        exam_names = {
            "UPSC": "UPSC Civil Services",
            "SSC": "SSC CGL",
            "IBPS": "IBPS PO",
            "RRB": "RRB NTPC",
            "GATE": "GATE",
            "ESE": "Engineering Services",
            "PSC": "State PSC",
            "DEFENCE": "Defence Exams"
        }


        # Add display name to every selected exam
        for exam in user_exams:

            code = str(exam["exam_code"]).upper()

            exam["exam_name"] = exam_names.get(
                code,
                code
            )

        selected_exam["exam_name"] = exam_names.get(
            str(selected_exam["exam_code"]).upper(),
            selected_exam["exam_code"]
        )


        # =====================================================
        # 8. SEND DATA TO HTML
        # =====================================================

        return render_template(
            "syllabus.html",
            exams=user_exams,
            subjects=subjects,
            selected_exam=selected_exam,
            subject_count=len(subjects),
            topic_count=total_topics,
            overall_progress=overall_progress,
            user_name=session.get("user_name", "User")
        )


    except Exception as e:

        print("========================================")
        print("SYLLABUS ERROR:", repr(e))
        print("========================================")

        flash(
            "Unable to load syllabus.",
            "error"
        )

        return redirect(url_for("dashboard"))


    finally:

        if conn:
            conn.close()
# ============================================================
# LOGOUT
# ============================================================
@app.route("/notifications")
def notifications():
    return  render_template("notifications")

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("landing"))


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)