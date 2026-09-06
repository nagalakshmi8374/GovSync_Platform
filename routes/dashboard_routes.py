from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from config.database import get_db_connection
from utils.auth import login_required

dashboard_bp = Blueprint("dashboard", __name__)

EXAM_NAMES = {
    "UPSC": "UPSC Civil Services", "SSC": "SSC CGL", "IBPS": "IBPS PO",
    "RRB": "RRB NTPC", "GATE": "GATE", "ESE": "Engineering Services",
    "PSC": "State PSC", "DEFENCE": "Defence Exams"
}

def time_ago(dt):
    if not dt:
        return ""
    days = (datetime.now() - dt.replace(tzinfo=None)).days
    if days <= 0: return "Today"
    if days == 1: return "Yesterday"
    if days < 7: return f"{days} days ago"
    if days < 30: return f"{days // 7} week{'s' if days // 7 != 1 else ''} ago"
    return f"{days // 30} month{'s' if days // 30 != 1 else ''} ago"

def user_exam_codes(cur, user_id):
    cur.execute("SELECT exam_code FROM user_exams WHERE user_id=%s ORDER BY id", (user_id,))
    return [str(r["exam_code"]).upper() for r in cur.fetchall()]

def fetch_updates(cur, exam_codes, limit=None):
    if exam_codes:
        cur.execute(
            """SELECT id, exam_code, title, description, updated_section, change_type, created_at
               FROM syllabus_updates
               WHERE exam_code IS NULL OR UPPER(exam_code)=ANY(%s)
               ORDER BY created_at DESC""" + (" LIMIT %s" if limit else ""),
            (exam_codes, limit) if limit else (exam_codes,)
        )
    else:
        cur.execute(
            """SELECT id, exam_code, title, description, updated_section, change_type, created_at
               FROM syllabus_updates WHERE exam_code IS NULL ORDER BY created_at DESC""" + (" LIMIT %s" if limit else ""),
            (limit,) if limit else ()
        )
    result=[]
    for r in cur.fetchall():
        code = str(r["exam_code"]).upper() if r["exam_code"] else None
        result.append({**r, "exam_code": code, "exam_name": EXAM_NAMES.get(code, code) if code else "All Exams",
                       "time_text": time_ago(r["created_at"]),
                       "is_new": r["created_at"] is not None and (datetime.now()-r["created_at"].replace(tzinfo=None)).days < 7})
    return result

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    uid=session["user_id"]; conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT ue.id user_exam_id, ue.exam_code,
                    COUNT(t.id) total_topics,
                    COUNT(p.topic_id) FILTER (WHERE p.completed=TRUE) completed_topics
                    FROM user_exams ue CROSS JOIN topics t
                    JOIN subjects s ON s.id=t.subject_id
                      AND UPPER(s.subject_code) IN ('REASONING','QUANT','ENGLISH','AWARENESS')
                    LEFT JOIN user_topic_progress p ON p.topic_id=t.id AND p.user_exam_id=ue.id
                    WHERE ue.user_id=%s GROUP BY ue.id, ue.exam_code ORDER BY ue.id""",(uid,))
            rows=cur.fetchall()
            exams=[]; total=done=0
            for r in rows:
                tt=r["total_topics"] or 0; dd=r["completed_topics"] or 0
                pct=round(dd/tt*100) if tt else 0
                exams.append({"exam_code":str(r["exam_code"]).upper(),"exam_name":EXAM_NAMES.get(str(r["exam_code"]).upper(),r["exam_code"]),
                              "progress":pct,"completed_topics":dd,"total_topics":tt})
                total += tt; done += dd
            overall=round(done/total*100) if total else 0
            codes=user_exam_codes(cur,uid)
            updates=fetch_updates(cur,codes,3)
            cur.execute("SELECT full_name,email,phone_number,preparation_type FROM users WHERE id=%s",(uid,))
            profile=cur.fetchone()
        return render_template("dashboard.html", today=datetime.now(), exams=exams, exam_count=len(exams),
            overall_progress=overall, topics_completed=done, recent_updates=updates,
            updates_count=len(fetch_updates(get_db_connection().cursor(),codes)) if False else len(updates), profile=profile)
    finally:
        conn.close()

@dashboard_bp.route("/progress")
@login_required
def progress():
    uid=session["user_id"]; conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT ue.id user_exam_id, ue.exam_code, COUNT(t.id) total_topics,
                    COUNT(p.topic_id) FILTER (WHERE p.completed=TRUE) completed_topics
                    FROM user_exams ue CROSS JOIN topics t JOIN subjects s ON s.id=t.subject_id
                    AND UPPER(s.subject_code) IN ('REASONING','QUANT','ENGLISH','AWARENESS')
                    LEFT JOIN user_topic_progress p ON p.topic_id=t.id AND p.user_exam_id=ue.id
                    WHERE ue.user_id=%s GROUP BY ue.id,ue.exam_code ORDER BY ue.id""",(uid,))
            exams=[]; done=total=0
            for r in cur.fetchall():
                tt=r["total_topics"] or 0; dd=r["completed_topics"] or 0; pct=round(dd/tt*100) if tt else 0
                status="Getting Started" if pct==0 else "Completed" if pct>=100 else "In Progress"
                code=str(r["exam_code"]).upper()
                exams.append({"exam_code":code,"exam_name":EXAM_NAMES.get(code,code),"progress":pct,"completed_topics":dd,"total_topics":tt,"status":status})
                total+=tt; done+=dd
            cur.execute("""SELECT ue.exam_code,t.topic_name,p.completed_at FROM user_topic_progress p
                JOIN user_exams ue ON ue.id=p.user_exam_id JOIN topics t ON t.id=p.topic_id
                WHERE ue.user_id=%s AND p.completed=TRUE ORDER BY p.completed_at DESC LIMIT 5""",(uid,))
            activity=[{"exam_name":EXAM_NAMES.get(str(r["exam_code"]).upper(),str(r["exam_code"]).upper()),"topic_name":r["topic_name"],"time_text":time_ago(r["completed_at"])} for r in cur.fetchall()]
        overall=round(done/total*100) if total else 0
        return render_template("progress.html",exams=exams,exam_count=len(exams),overall_progress=overall,topics_completed=done,topics_remaining_pct=100-overall,recent_activity=activity,user_name=session.get("user_name","User"))
    finally: conn.close()

@dashboard_bp.route("/updates")
@login_required
def updates():
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            codes=user_exam_codes(cur,session["user_id"]); rows=fetch_updates(cur,codes)
        return render_template("updates.html",updates=rows,total_updates=len(rows),
            new_updates=sum(u["is_new"] for u in rows),exams_updated=len({u["exam_code"] for u in rows if u["exam_code"]}),
            filter_exams=[{"code":c,"name":EXAM_NAMES.get(c,c)} for c in codes],user_name=session.get("user_name","User"))
    finally: conn.close()

@dashboard_bp.route("/myexams")
@login_required
def myexams():
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT exam_code FROM user_exams WHERE user_id=%s ORDER BY id",(session["user_id"],))
            exams=[r["exam_code"] for r in cur.fetchall()]
        return render_template("my_exams.html",exams=exams,user_name=session.get("user_name","User"),user_email=session.get("user_email",""))
    finally: conn.close()

@dashboard_bp.route("/api/topic-progress",methods=["POST"])
@login_required
def topic_progress():
    data=request.get_json() or {}; exam_id=data.get("user_exam_id"); topic_id=data.get("topic_id"); completed=data.get("completed")
    if not exam_id or not topic_id or not isinstance(completed,bool): return {"success":False,"message":"Missing or invalid data."},400
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM user_exams WHERE id=%s AND user_id=%s",(exam_id,session["user_id"]))
            if not cur.fetchone(): return {"success":False,"message":"Invalid exam."},403
            cur.execute("""SELECT id FROM topics WHERE id=%s""",(topic_id,))
            if not cur.fetchone(): return {"success":False,"message":"Invalid topic."},400
            cur.execute("""INSERT INTO user_topic_progress(user_exam_id,topic_id,completed,completed_at)
                VALUES(%s,%s,%s,CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END)
                ON CONFLICT(user_exam_id,topic_id) DO UPDATE SET completed=EXCLUDED.completed,completed_at=EXCLUDED.completed_at""",
                (exam_id,topic_id,completed,completed))
        conn.commit(); return {"success":True}
    except Exception as exc:
        conn.rollback(); print("TOPIC PROGRESS ERROR:",repr(exc)); return {"success":False,"message":"Could not save progress."},500
    finally: conn.close()

@dashboard_bp.route("/syllabus")
@login_required
def syllabus():
    conn=get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,exam_code FROM user_exams WHERE user_id=%s ORDER BY id",(session["user_id"],))
            user_exams=cur.fetchall()
            if not user_exams:
                flash("Please select at least one exam first.","error"); return redirect(url_for("preferences.preference"))
            requested=request.args.get("exam","").strip().upper()
            selected=next((e for e in user_exams if str(e["exam_code"]).upper()==requested),user_exams[0])
            cur.execute("""SELECT s.id subject_id,s.subject_code,s.subject_name,t.id topic_id,t.topic_name,
                COALESCE(p.completed,FALSE) completed FROM subjects s LEFT JOIN topics t ON t.subject_id=s.id
                LEFT JOIN user_topic_progress p ON p.topic_id=t.id AND p.user_exam_id=%s
                WHERE UPPER(s.subject_code) IN ('REASONING','QUANT','ENGLISH','AWARENESS') ORDER BY s.id,t.id""",(selected["id"],))
            rows=cur.fetchall()
        subjects={c:{"id":None,"code":c,"name":"","topics":[],"progress":0} for c in ["REASONING","QUANT","ENGLISH","AWARENESS"]}
        for r in rows:
            c=str(r["subject_code"]).upper(); subjects[c]["id"]=r["subject_id"]; subjects[c]["name"]=r["subject_name"]
            if r["topic_id"] is not None: subjects[c]["topics"].append({"id":r["topic_id"],"name":r["topic_name"],"completed":r["completed"]})
        total=done=0
        for s in subjects.values():
            d=sum(1 for t in s["topics"] if t["completed"]); n=len(s["topics"]); s["progress"]=round(d/n*100) if n else 0; total+=n; done+=d
        for e in user_exams:
            e["exam_name"]=EXAM_NAMES.get(str(e["exam_code"]).upper(),str(e["exam_code"]))
        selected["exam_name"]=EXAM_NAMES.get(str(selected["exam_code"]).upper(),str(selected["exam_code"]))
        return render_template("syllabus.html",exams=user_exams,subjects=subjects,selected_exam=selected,subject_count=len(subjects),topic_count=total,overall_progress=round(done/total*100) if total else 0,user_name=session.get("user_name","User"))
    finally: conn.close()
