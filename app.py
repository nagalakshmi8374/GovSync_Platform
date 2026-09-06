import os
from flask import Flask, render_template
from config.config import Config
from config.database import get_db_connection

from routes.auth_routes import auth_bp
from routes.preference_routes import preferences_bp
from routes.profile_routes import profile_bp
from routes.dashboard_routes import dashboard_bp
from routes.notification_routes import notifications_bp
from routes.admin_routes import admin_bp

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["JSON_SORT_KEYS"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

    app.register_blueprint(auth_bp)
    app.register_blueprint(preferences_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def landing():
        return render_template("landing.html")

    return app

def initialize_database():
    """Apply the idempotent PostgreSQL schema. Existing rows are preserved."""
    schema_path = os.path.join(os.path.dirname(__file__), "database", "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as file:
        sql = file.read()
    # psycopg can execute the schema as one SQL string for PostgreSQL.
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()

app = create_app()

if __name__ == "__main__":
    if os.getenv("AUTO_INIT_DB", "true").lower() == "true":
        try:
            initialize_database()
            print("Database schema is ready.")
        except Exception as exc:
            print("DATABASE INITIALIZATION ERROR:", repr(exc))
            print("Make sure PostgreSQL is running and DATABASE_URL is correct.")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "true").lower()=="true")
