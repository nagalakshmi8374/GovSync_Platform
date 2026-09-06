from flask import Blueprint, render_template, jsonify, session
from config.database import get_db_connection
from utils.auth import login_required

notifications_bp=Blueprint("notifications",__name__)

@notifications_bp.route("/notifications")
@login_required
def notifications():
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT n.id,n.title,n.message,n.exam_code,n.priority,n.created_at,nr.is_read
                          FROM notification_recipients nr JOIN notifications n ON n.id=nr.notification_id
                          WHERE nr.user_id=%s ORDER BY n.created_at DESC""",(session["user_id"],))
            rows=cur.fetchall()
        return render_template("notifications.html", notifications=rows,
                               unread_count=sum(1 for r in rows if not r["is_read"]))
    finally: conn.close()

@notifications_bp.route("/api/notifications/<int:notification_id>/read",methods=["POST"])
@login_required
def mark_read(notification_id):
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""UPDATE notification_recipients SET is_read=TRUE,read_at=CURRENT_TIMESTAMP
                           WHERE notification_id=%s AND user_id=%s""",(notification_id,session["user_id"]))
            if cur.rowcount==0:return {"success":False,"message":"Notification not found."},404
        conn.commit(); return {"success":True}
    finally: conn.close()

@notifications_bp.route("/api/notifications/read-all",methods=["POST"])
@login_required
def mark_all_read():
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""UPDATE notification_recipients SET is_read=TRUE,read_at=CURRENT_TIMESTAMP
                           WHERE user_id=%s AND is_read=FALSE""",(session["user_id"],))
        conn.commit(); return {"success":True}
    finally: conn.close()
