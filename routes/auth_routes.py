from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timezone
from config.database import get_db_connection
from config.config import Config
from services.otp_service import generate_otp, hash_otp, otp_expiry
from services.email_service import send_password_reset_otp
from utils.password import hash_password, verify_password
from utils.auth import is_admin_user

auth_bp = Blueprint("auth", __name__)

def _login_user(user):
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user.get("full_name") or "User"
    session["user_email"] = user["email"]
    session["is_admin"] = is_admin_user(user)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Please enter your email and password.", "error")
            return redirect(url_for("auth.login"))

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id, full_name, email, password_hash, password, role, preferences_completed FROM users WHERE LOWER(email) = %s", (email,))
                user = cur.fetchone()

                if not user:
                    flash("Invalid email or password.", "error")
                    return redirect(url_for("auth.login"))

                stored_hash = user["password_hash"] or user["password"]
                if not verify_password(stored_hash, password):
                    flash("Invalid email or password.", "error")
                    return redirect(url_for("auth.login"))

                # Migrate a legacy hash from the old password column.
                if not user["password_hash"] and user["password"]:
                    cur.execute("UPDATE users SET password_hash = %s, password = NULL WHERE id = %s", (hash_password(password), user["id"]))
                    conn.commit()

                _login_user(user)

            if session["is_admin"]:
                return redirect(url_for("admin.admin_dashboard"))
            if not user["preferences_completed"]:
                return redirect(url_for("preferences.preference"))
            return redirect(url_for("dashboard.dashboard"))
        except Exception as exc:
            if conn:
                conn.rollback()
            print("LOGIN ERROR:", repr(exc))
            flash("Something went wrong while logging in.", "error")
            return redirect(url_for("auth.login"))
        finally:
            if conn:
                conn.close()

    return render_template("login.html")

@auth_bp.route("/register", methods=["POST"])
def register():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not full_name or not email or not password or not confirm_password:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("auth.login"))
    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("auth.login"))
    if len(password) < 8:
        flash("Password must contain at least 8 characters.", "error")
        return redirect(url_for("auth.login"))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE LOWER(email) = %s", (email,))
            if cur.fetchone():
                flash("An account with this email already exists.", "error")
                return redirect(url_for("auth.login"))

            cur.execute(
                """INSERT INTO users (full_name, email, password_hash, preferences_completed)
                   VALUES (%s, %s, %s, FALSE)""",
                (full_name, email, hash_password(password))
            )
        conn.commit()
        flash("Account created successfully. Please sign in.", "success")
    except Exception as exc:
        if conn:
            conn.rollback()
        print("REGISTER ERROR:", repr(exc))
        flash("Something went wrong while creating your account.", "error")
    finally:
        if conn:
            conn.close()
    return redirect(url_for("auth.login"))

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter your registered email address.", "error")
            return redirect(url_for("auth.forgot_password"))

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id, email, full_name FROM users WHERE LOWER(email) = %s", (email,))
                user = cur.fetchone()
                if not user:
                    flash("No account is registered with that email address.", "error")
                    return redirect(url_for("auth.forgot_password"))

                # Invalidate older reset requests.
                cur.execute("UPDATE password_reset_otps SET used = TRUE WHERE user_id = %s AND used = FALSE", (user["id"],))
                otp = generate_otp()
                cur.execute(
                    """INSERT INTO password_reset_otps (user_id, otp_hash, expires_at)
                       VALUES (%s, %s, %s) RETURNING id""",
                    (user["id"], hash_otp(otp), otp_expiry(Config.OTP_EXPIRY_MINUTES))
                )
                reset_id = cur.fetchone()["id"]
                conn.commit()

            try:
                send_password_reset_otp(user["email"], otp, Config.OTP_EXPIRY_MINUTES)
            except Exception:
                with conn.cursor() as cur:
                    cur.execute("UPDATE password_reset_otps SET used = TRUE WHERE id = %s", (reset_id,))
                conn.commit()
                raise

            session["otp_reset_id"] = reset_id
            session["otp_email"] = user["email"]
            flash("A password reset OTP has been sent to your email.", "success")
            return redirect(url_for("auth.verify_otp"))
        except Exception as exc:
            if conn:
                conn.rollback()
            print("FORGOT PASSWORD ERROR:", repr(exc))
            flash("We could not send the OTP. Please check the email configuration and try again.", "error")
            return redirect(url_for("auth.forgot_password"))
        finally:
            if conn:
                conn.close()

    return render_template("forgot_password.html")

@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    reset_id = session.get("otp_reset_id")
    if not reset_id:
        flash("Please request a new OTP first.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, otp_hash, expires_at, attempts, used
                       FROM password_reset_otps WHERE id = %s""",
                    (reset_id,)
                )
                record = cur.fetchone()

                if not record or record["used"]:
                    flash("This OTP is no longer valid. Please request a new one.", "error")
                    return redirect(url_for("auth.forgot_password"))

                now = datetime.now(timezone.utc)
                expires = record["expires_at"]
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)

                if expires <= now:
                    cur.execute("UPDATE password_reset_otps SET used = TRUE WHERE id = %s", (reset_id,))
                    conn.commit()
                    flash("This OTP has expired. Please request a new one.", "error")
                    return redirect(url_for("auth.forgot_password"))

                if record["attempts"] >= 5:
                    cur.execute("UPDATE password_reset_otps SET used = TRUE WHERE id = %s", (reset_id,))
                    conn.commit()
                    flash("Too many incorrect attempts. Please request a new OTP.", "error")
                    return redirect(url_for("auth.forgot_password"))

                cur.execute("UPDATE password_reset_otps SET attempts = attempts + 1 WHERE id = %s", (reset_id,))
                if hash_otp(otp) != record["otp_hash"]:
                    conn.commit()
                    flash("Incorrect OTP. Please try again.", "error")
                    return redirect(url_for("auth.verify_otp"))

                cur.execute("UPDATE password_reset_otps SET verified_at = CURRENT_TIMESTAMP WHERE id = %s", (reset_id,))
                conn.commit()
                session["otp_verified"] = True
                return redirect(url_for("auth.reset_password"))
        except Exception as exc:
            if conn:
                conn.rollback()
            print("OTP VERIFY ERROR:", repr(exc))
            flash("Unable to verify the OTP.", "error")
        finally:
            if conn:
                conn.close()

    return render_template("verify_otp.html", email=session.get("otp_email", ""))

@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get("otp_reset_id") or not session.get("otp_verified"):
        flash("Please verify your OTP first.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(new_password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return redirect(url_for("auth.reset_password"))
        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("auth.reset_password"))

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, verified_at, used FROM password_reset_otps WHERE id = %s", (session["otp_reset_id"],))
                reset = cur.fetchone()
                if not reset or reset["used"] or not reset["verified_at"]:
                    flash("This reset request is no longer valid.", "error")
                    return redirect(url_for("auth.forgot_password"))

                cur.execute(
                    "UPDATE users SET password_hash = %s, password = NULL WHERE id = %s",
                    (hash_password(new_password), reset["user_id"])
                )
                cur.execute("UPDATE password_reset_otps SET used = TRUE WHERE id = %s", (session["otp_reset_id"],))
            conn.commit()
            for key in ("otp_reset_id", "otp_email", "otp_verified"):
                session.pop(key, None)
            flash("Password reset successfully. You can now sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
        except Exception as exc:
            if conn:
                conn.rollback()
            print("RESET PASSWORD ERROR:", repr(exc))
            flash("Could not reset your password.", "error")
        finally:
            if conn:
                conn.close()

    return render_template("reset_password.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("landing"))
