from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import sqlite3, os, secrets, hmac
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-development-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER", "").lower() == "true",
)
DB_PATH = os.path.join(os.path.dirname(__file__), "raktsetu.db")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_error):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('donor','patient','hospital','ngo','admin')),
        blood_group TEXT,
        city TEXT,
        phone TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS blood_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT NOT NULL,
        blood_group TEXT NOT NULL,
        units INTEGER NOT NULL,
        city TEXT NOT NULL,
        hospital TEXT NOT NULL,
        contact TEXT NOT NULL,
        details TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        verified_by INTEGER,
        deleted_at TEXT,
        FOREIGN KEY(created_by) REFERENCES users(id),
        FOREIGN KEY(verified_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        donor_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'interested',
        created_at TEXT NOT NULL,
        UNIQUE(request_id, donor_id),
        FOREIGN KEY(request_id) REFERENCES blood_requests(id),
        FOREIGN KEY(donor_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS camps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        organizer TEXT NOT NULL,
        city TEXT NOT NULL,
        event_date TEXT NOT NULL,
        details TEXT,
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(created_by) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS request_activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        actor_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        old_status TEXT,
        new_status TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(request_id) REFERENCES blood_requests(id),
        FOREIGN KEY(actor_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS camp_signups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camp_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(camp_id, user_id),
        FOREIGN KEY(camp_id) REFERENCES camps(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    # Safe, additive migration for databases created by earlier RaktSetu versions.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(blood_requests)")}
    if "deleted_at" not in columns:
        conn.execute("ALTER TABLE blood_requests ADD COLUMN deleted_at TEXT")
    conn.commit()
    conn.close()

def log_request_activity(conn, request_id, actor_id, action, old_status=None, new_status=None):
    conn.execute("""INSERT INTO request_activity
        (request_id,actor_id,action,old_status,new_status,created_at)
        VALUES(?,?,?,?,?,?)""",
        (request_id, actor_id, action, old_status, new_status, datetime.now().isoformat(timespec="minutes")))

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return decorator
    return decorator

@app.before_request
def protect_post_requests():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not submitted or not hmac.compare_digest(submitted, expected):
            return "Invalid or missing security token. Reload the page and try again.", 400

@app.context_processor
def inject_user():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    user = None
    if session.get("user_id"):
        user = db().execute("SELECT id,name,email,role,blood_group,city FROM users WHERE id=?",
                            (session["user_id"],)).fetchone()
    return {"current_user": user, "csrf_token": session["csrf_token"]}

@app.route("/")
def index():
    conn = db()
    stats = {
        "donors": conn.execute("SELECT COUNT(*) FROM users WHERE role='donor'").fetchone()[0],
        "requests": conn.execute("SELECT COUNT(*) FROM blood_requests WHERE deleted_at IS NULL AND status IN ('pending','verified','in_progress')").fetchone()[0],
        "camps": conn.execute("SELECT COUNT(*) FROM camps").fetchone()[0]
    }
    latest = conn.execute("""SELECT * FROM blood_requests WHERE deleted_at IS NULL AND status IN ('pending','verified','in_progress')
                             ORDER BY id DESC LIMIT 5""").fetchall()
    return render_template("index.html", stats=stats, latest=latest)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        blood = request.form.get("blood_group") or None
        city = request.form.get("city", "").strip()
        phone = request.form.get("phone", "").strip()
        if not name or not email or len(password) < 8 or role not in ("donor","patient","hospital","ngo"):
            flash("Please complete all required fields. Password must be at least 8 characters.", "danger")
            return render_template("register.html")
        try:
            db().execute("""INSERT INTO users(name,email,password_hash,role,blood_group,city,phone,created_at)
                            VALUES(?,?,?,?,?,?,?,?)""",
                         (name,email,generate_password_hash(password),role,blood,city,phone,datetime.now().isoformat(timespec="minutes")))
            db().commit()
            flash("Account created. You can now log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = db()
    role = session["role"]
    uid = session["user_id"]
    if role == "donor":
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        requests = conn.execute("""SELECT * FROM blood_requests
            WHERE status='verified' AND blood_group=? AND lower(city)=lower(?)
            ORDER BY id DESC""", (user["blood_group"], user["city"])).fetchall()
        responses = conn.execute("""SELECT r.*, br.patient_name, br.blood_group, br.city
            FROM responses r JOIN blood_requests br ON br.id=r.request_id
            WHERE r.donor_id=? ORDER BY r.id DESC""", (uid,)).fetchall()
        return render_template("dashboard_donor.html", requests=requests, responses=responses)
    if role == "patient":
        own = conn.execute("SELECT * FROM blood_requests WHERE created_by=? AND deleted_at IS NULL ORDER BY id DESC", (uid,)).fetchall()
        return render_template("dashboard_requester.html", requests=own, view_role=role)
    if role == "hospital":
        all_requests = conn.execute("""SELECT br.*,u.name AS creator FROM blood_requests br
            JOIN users u ON u.id=br.created_by
            WHERE br.deleted_at IS NULL AND br.status IN ('pending','verified','in_progress')
            ORDER BY CASE br.status WHEN 'pending' THEN 0 WHEN 'verified' THEN 1 ELSE 2 END, br.id DESC""").fetchall()
        return render_template("dashboard_requester.html", requests=all_requests, view_role=role)
    if role == "ngo":
        camps = conn.execute("SELECT * FROM camps WHERE created_by=? ORDER BY event_date", (uid,)).fetchall()
        return render_template("dashboard_ngo.html", camps=camps)
    if role == "admin":
        requests = conn.execute("SELECT br.*,u.name AS creator FROM blood_requests br JOIN users u ON u.id=br.created_by WHERE br.deleted_at IS NULL ORDER BY br.id DESC").fetchall()
        activity = conn.execute("""SELECT a.*,u.name AS actor_name,br.patient_name
            FROM request_activity a JOIN users u ON u.id=a.actor_id
            JOIN blood_requests br ON br.id=a.request_id
            ORDER BY a.id DESC LIMIT 30""").fetchall()
        return render_template("dashboard_admin.html", requests=requests, activity=activity)
    return redirect(url_for("index"))

@app.route("/request/new", methods=["GET", "POST"])
@login_required
@role_required("patient","hospital")
def new_request():
    if request.method == "POST":
        f = request.form
        required_values = [f.get(key, "").strip() for key in ("patient_name", "blood_group", "city", "hospital", "contact")]
        if not all(required_values) or f.get("blood_group") not in ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"):
            flash("Please provide all required details and select a valid blood group.", "danger")
            return render_template("new_request.html")
        try:
            units = int(f.get("units", "1"))
            if units < 1 or units > 20:
                raise ValueError()
        except ValueError:
            flash("Units must be between 1 and 20.", "danger")
            return render_template("new_request.html")
        cursor = db().execute("""INSERT INTO blood_requests
            (patient_name,blood_group,units,city,hospital,contact,details,created_by,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (f.get("patient_name","").strip(),f.get("blood_group"),units,f.get("city","").strip(),
             f.get("hospital","").strip(),f.get("contact","").strip(),f.get("details","").strip(),
             session["user_id"],datetime.now().isoformat(timespec="minutes")))
        log_request_activity(db(), cursor.lastrowid, session["user_id"], "created", None, "pending")
        db().commit()
        flash("Blood request submitted. It will appear to donors after hospital/admin verification.", "success")
        return redirect(url_for("dashboard"))
    return render_template("new_request.html")

@app.route("/request/<int:request_id>/respond", methods=["POST"])
@login_required
@role_required("donor")
def respond(request_id):
    conn = db()
    req = conn.execute("SELECT * FROM blood_requests WHERE id=? AND status='verified'", (request_id,)).fetchone()
    donor = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not req or req["blood_group"] != donor["blood_group"] or req["city"].lower() != (donor["city"] or "").lower():
        flash("This request is not an exact blood-group and city match.", "warning")
    else:
        try:
            conn.execute("INSERT INTO responses(request_id,donor_id,created_at) VALUES(?,?,?)",
                         (request_id,session["user_id"],datetime.now().isoformat(timespec="minutes")))
            conn.commit()
            flash("Your interest has been shared with the requester. Confirm details directly before travelling.", "success")
        except sqlite3.IntegrityError:
            flash("You have already responded to this request.", "info")
    return redirect(url_for("dashboard"))

@app.route("/request/<int:request_id>/verify", methods=["POST"])
@login_required
@role_required("hospital","admin")
def verify_request(request_id):
    conn = db()
    req = conn.execute("SELECT * FROM blood_requests WHERE id=? AND deleted_at IS NULL", (request_id,)).fetchone()
    if not req:
        flash("Request not found.", "warning")
    elif req["status"] != "pending":
        flash("Only pending requests can be verified.", "warning")
    else:
        conn.execute("UPDATE blood_requests SET status='verified', verified_by=? WHERE id=?",
                     (session["user_id"], request_id))
        log_request_activity(conn, request_id, session["user_id"], "verified", req["status"], "verified")
        conn.commit()
        flash("Request verified. Matching donors can now view it.", "success")
    return redirect(url_for("dashboard"))

@app.route("/request/<int:request_id>/progress", methods=["POST"])
@login_required
@role_required("hospital", "admin")
def progress_request(request_id):
    conn = db()
    req = conn.execute("SELECT * FROM blood_requests WHERE id=? AND deleted_at IS NULL", (request_id,)).fetchone()
    if not req or req["status"] != "verified":
        flash("Only verified requests can be moved into progress.", "warning")
    else:
        conn.execute("UPDATE blood_requests SET status='in_progress' WHERE id=?", (request_id,))
        log_request_activity(conn, request_id, session["user_id"], "marked_in_progress", "verified", "in_progress")
        conn.commit()
        flash("Request marked as in progress.", "success")
    return redirect(url_for("dashboard"))

@app.route("/request/<int:request_id>/complete", methods=["POST"])
@login_required
@role_required("hospital", "admin")
def complete_request(request_id):
    conn = db()
    req = conn.execute("SELECT * FROM blood_requests WHERE id=? AND deleted_at IS NULL", (request_id,)).fetchone()
    if not req or req["status"] not in ("verified", "in_progress"):
        flash("Only verified or in-progress requests can be completed.", "warning")
    else:
        conn.execute("UPDATE blood_requests SET status='completed' WHERE id=?", (request_id,))
        log_request_activity(conn, request_id, session["user_id"], "completed", req["status"], "completed")
        conn.commit()
        flash("Request marked as completed.", "success")
    return redirect(url_for("dashboard"))

@app.route("/request/<int:request_id>/cancel", methods=["POST"])
@login_required
@role_required("patient", "admin")
def cancel_request(request_id):
    conn = db()
    req = conn.execute("SELECT * FROM blood_requests WHERE id=? AND deleted_at IS NULL", (request_id,)).fetchone()
    allowed = req and (session["role"] == "admin" or req["created_by"] == session["user_id"])
    if not allowed:
        flash("You cannot cancel this request.", "danger")
    elif req["status"] not in ("pending", "verified"):
        flash("Only pending or verified requests can be cancelled.", "warning")
    else:
        conn.execute("UPDATE blood_requests SET status='cancelled' WHERE id=?", (request_id,))
        log_request_activity(conn, request_id, session["user_id"], "cancelled", req["status"], "cancelled")
        conn.commit()
        flash("Request cancelled. Its history has been retained.", "success")
    return redirect(url_for("dashboard"))

@app.route("/request/<int:request_id>/delete", methods=["POST"])
@login_required
@role_required("patient", "admin")
def delete_request(request_id):
    conn = db()
    req = conn.execute("SELECT * FROM blood_requests WHERE id=? AND deleted_at IS NULL", (request_id,)).fetchone()
    allowed = req and (session["role"] == "admin" or req["created_by"] == session["user_id"])
    if not allowed:
        flash("You cannot archive this request.", "danger")
    elif req["status"] not in ("completed", "cancelled", "closed"):
        flash("Only completed or cancelled requests can be archived.", "warning")
    else:
        now = datetime.now().isoformat(timespec="minutes")
        conn.execute("UPDATE blood_requests SET deleted_at=? WHERE id=?", (now, request_id))
        log_request_activity(conn, request_id, session["user_id"], "archived", req["status"], req["status"])
        conn.commit()
        flash("Request archived. The audit history remains available to administrators.", "success")
    return redirect(url_for("dashboard"))

# Backward-compatible endpoint for older dashboard links.
@app.route("/request/<int:request_id>/close", methods=["POST"])
@login_required
def close_request(request_id):
    return complete_request(request_id) if session.get("role") in ("hospital", "admin") else redirect(url_for("dashboard"))

@app.route("/camps")
def camps():
    items = db().execute("""SELECT c.*,u.name AS organizer_name,
        (SELECT COUNT(*) FROM camp_signups s WHERE s.camp_id=c.id) AS signups
        FROM camps c JOIN users u ON u.id=c.created_by ORDER BY c.event_date""").fetchall()
    return render_template("camps.html", camps=items)

@app.route("/camp/new", methods=["GET", "POST"])
@login_required
@role_required("ngo","admin")
def new_camp():
    if request.method == "POST":
        f = request.form
        db().execute("""INSERT INTO camps(title,organizer,city,event_date,details,created_by,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (f.get("title","").strip(),f.get("organizer","").strip(),f.get("city","").strip(),
             f.get("event_date"),f.get("details","").strip(),session["user_id"],datetime.now().isoformat(timespec="minutes")))
        db().commit()
        flash("Camp published.", "success")
        return redirect(url_for("camps"))
    return render_template("new_camp.html")

@app.route("/camp/<int:camp_id>/join", methods=["POST"])
@login_required
@role_required("donor")
def join_camp(camp_id):
    try:
        db().execute("INSERT INTO camp_signups(camp_id,user_id,created_at) VALUES(?,?,?)",
                     (camp_id,session["user_id"],datetime.now().isoformat(timespec="minutes")))
        db().commit()
        flash("You are registered for this camp. The organizer should confirm the details.", "success")
    except sqlite3.IntegrityError:
        flash("You have already registered for this camp.", "info")
    return redirect(url_for("camps"))

@app.route("/admin")
@login_required
@role_required("admin")
def admin():
    users = db().execute("SELECT id,name,email,role,blood_group,city FROM users ORDER BY id DESC").fetchall()
    responses = db().execute("""SELECT r.*,u.name AS donor_name,br.patient_name,br.blood_group
        FROM responses r JOIN users u ON u.id=r.donor_id JOIN blood_requests br ON br.id=r.request_id
        ORDER BY r.id DESC""").fetchall()
    return render_template("admin.html", users=users, responses=responses)

init_db()

if __name__ == "__main__":
    app.run(debug=False)
