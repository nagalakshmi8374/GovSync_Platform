from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from config.database import get_db_connection
from utils.auth import admin_required
from routes.dashboard_routes import EXAM_NAMES

admin_bp = Blueprint("admin", __name__)

def exams_from_db(cur):
    cur.execute("SELECT DISTINCT exam_code FROM user_exams ORDER BY exam_code")
    codes={str(r["exam_code"]).upper() for r in cur.fetchall()}
    codes |= set(EXAM_NAMES)
    return [{"code": c, "name": EXAM_NAMES.get(c,c)} for c in sorted(codes)]

@admin_bp.route("/admin")
@admin_required
def admin_dashboard():
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,exam_code,subject,topic,description,unit_module,priority,status FROM syllabus_entries ORDER BY updated_at DESC")
            syllabus=cur.fetchall()
            cur.execute("""SELECT n.id,n.title,n.message,n.exam_code,n.target_type,n.priority,n.created_at,
                           COUNT(nr.id) recipient_count
                           FROM notifications n LEFT JOIN notification_recipients nr ON nr.notification_id=n.id
                           GROUP BY n.id ORDER BY n.created_at DESC LIMIT 10""")
            notifications=cur.fetchall()
            cur.execute("SELECT id,full_name,email,role,created_at FROM users ORDER BY created_at DESC LIMIT 100")
            users=cur.fetchall()
            cur.execute("SELECT COUNT(*) count FROM users"); user_count=cur.fetchone()["count"]
        return render_template("admin.html", syllabus=syllabus, notifications=notifications, users=users, user_count=user_count, exams=exams_from_db(cur) if False else [{"code":c,"name":EXAM_NAMES.get(c,c)} for c in sorted(set(EXAM_NAMES))])
    finally: conn.close()

@admin_bp.route("/api/admin/syllabus",methods=["POST"])
@admin_required
def create_syllabus():
    data=request.get_json() or {}
    required=["exam_code","subject","topic"]
    if any(not str(data.get(k,"")).strip() for k in required):
        return {"success":False,"message":"Exam, subject and topic are required."},400
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO syllabus_entries(exam_code,subject,topic,description,unit_module,priority,status,created_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (str(data["exam_code"]).upper(),data["subject"].strip(),data["topic"].strip(),data.get("description","").strip(),data.get("unit_module","").strip(),data.get("priority","Medium"),data.get("status","Active"),session["user_id"]))
            new_id=cur.fetchone()["id"]
        conn.commit()
        return {"success":True,"id":new_id}
    except Exception as exc:
        conn.rollback(); print("CREATE SYLLABUS ERROR:",repr(exc)); return {"success":False,"message":"Could not add syllabus entry."},500
    finally: conn.close()

@admin_bp.route("/api/admin/syllabus/<int:entry_id>",methods=["PUT"])
@admin_required
def update_syllabus(entry_id):
    data=request.get_json() or {}
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""UPDATE syllabus_entries SET exam_code=%s,subject=%s,topic=%s,description=%s,unit_module=%s,
                           priority=%s,status=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                        (str(data.get("exam_code","")).upper(),data.get("subject","").strip(),data.get("topic","").strip(),
                         data.get("description","").strip(),data.get("unit_module","").strip(),data.get("priority","Medium"),
                         data.get("status","Active"),entry_id))
            if cur.rowcount==0: return {"success":False,"message":"Syllabus entry not found."},404
        conn.commit(); return {"success":True}
    except Exception as exc:
        conn.rollback(); print("UPDATE SYLLABUS ERROR:",repr(exc)); return {"success":False,"message":"Could not update syllabus."},500
    finally: conn.close()

@admin_bp.route("/api/admin/syllabus/<int:entry_id>",methods=["DELETE"])
@admin_required
def delete_syllabus(entry_id):
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM syllabus_entries WHERE id=%s",(entry_id,))
            if cur.rowcount==0:return {"success":False,"message":"Syllabus entry not found."},404
        conn.commit(); return {"success":True}
    except Exception as exc:
        conn.rollback(); print("DELETE SYLLABUS ERROR:",repr(exc)); return {"success":False,"message":"Could not delete syllabus."},500
    finally: conn.close()

@admin_bp.route("/api/admin/notifications",methods=["POST"])
@admin_required
def create_notification():
    data=request.get_json() or {}
    title=str(data.get("title","")).strip(); message=str(data.get("message","")).strip()
    target=str(data.get("target","all")).lower(); exam_code=(data.get("exam_code") or "").strip().upper() or None
    priority=str(data.get("priority","normal")).lower()
    if not title or not message:return {"success":False,"message":"Title and message are required."},400
    if target not in {"all","specific","exam"}:return {"success":False,"message":"Invalid target."},400
    if priority not in {"normal","important","urgent"}:return {"success":False,"message":"Invalid priority."},400
    if target=="exam" and not exam_code:return {"success":False,"message":"Select an exam."},400
    specific_ids=data.get("user_ids") or []
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO notifications(title,message,sender_admin_id,exam_code,target_type,priority)
                           VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",(title,message,session["user_id"],exam_code,target,priority))
            nid=cur.fetchone()["id"]
            if target=="all":
                cur.execute("SELECT id FROM users WHERE id <> %s",(session["user_id"],))
            elif target=="exam":
                cur.execute("SELECT DISTINCT user_id id FROM user_exams WHERE UPPER(exam_code)=%s",(exam_code,))
            else:
                # Only integer user IDs are accepted; the backend still controls the actual recipient lookup.
                ids=[int(x) for x in specific_ids if str(x).isdigit()]
                cur.execute("SELECT id FROM users WHERE id=ANY(%s)",(ids,))
            ids=[r["id"] for r in cur.fetchall()]
            if ids:
                cur.executemany("INSERT INTO notification_recipients(notification_id,user_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",[(nid,uid) for uid in ids])
        conn.commit(); return {"success":True,"notification_id":nid,"recipient_count":len(ids)}
    except Exception as exc:
        conn.rollback(); print("CREATE NOTIFICATION ERROR:",repr(exc)); return {"success":False,"message":"Could not send notification."},500
    finally: conn.close()
