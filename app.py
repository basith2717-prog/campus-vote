from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_wtf import CSRFProtect
from utils.db import get_conn
from utils.security import hash_password, verify_password
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from PIL import Image
import sqlite3, os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ---------------- SECRETS & CONFIG ----------------
app.secret_key = os.environ.get("SECRET_KEY") or "campusease-super-secret-key-2026"
is_production = os.environ.get("FLASK_ENV") == "production"

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=is_production,
    SESSION_COOKIE_SAMESITE="Lax"
)
ADMIN_PASS = os.environ.get("ADMIN_PASS") or "admin123"

# ---------------- CSRF ----------------
csrf = CSRFProtect(app)

# ---------------- FILE UPLOAD CONFIG ----------------
UPLOAD_FOLDER = os.path.join("static", "photos")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

STAGE_CONFIG = {
    1: {
        "title": "Class Election (CR)",
        "badge": "Step 1",
        "tag": "CLASS LEVEL",
        "next_stage": 2,
        "next_title": "Department Election"
    },
    2: {
        "title": "Department Election",
        "badge": "Step 2",
        "tag": "ACADEMIC FACULTY",
        "next_stage": 3,
        "next_title": "University Council"
    },
    3: {
        "title": "University Council",
        "badge": "Step 3",
        "tag": "EXECUTIVE COUNCIL",
        "next_stage": 4,
        "next_title": "Campus Policies & Committees"
    },
    4: {
        "title": "Campus Policies & Committees",
        "badge": "Step 4",
        "tag": "CAMPUS REFERENDUM",
        "next_stage": None,
        "next_title": None
    }
}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------- HELPERS ----------------
def row_to_dict(row):
    return dict(row) if row else None


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def expire_elections():
    """Automatically marks elections as inactive if their end_time has passed."""
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute(
        "UPDATE elections SET is_active=0 WHERE is_active=1 AND end_time < ?",
        (now,)
    )
    conn.commit()
    conn.close()


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- DB INIT & MULTI-STAGE SCHEMA ----------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        college_id TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        department TEXT DEFAULT 'Computer Science',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS elections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        stage INTEGER NOT NULL DEFAULT 1,
        category_name TEXT NOT NULL,
        description TEXT,
        is_active INTEGER DEFAULT 1,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        photo TEXT,
        manifesto TEXT,
        promoted_from_stage INTEGER DEFAULT NULL,
        promotion_status TEXT DEFAULT NULL,
        FOREIGN KEY (election_id) REFERENCES elections (id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        election_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        candidate_id INTEGER NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(election_id, student_id),
        FOREIGN KEY (election_id) REFERENCES elections (id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
        FOREIGN KEY (candidate_id) REFERENCES candidates (id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()


def seed_data():
    conn = get_conn()
    cur = conn.cursor()

    # Seed demo students
    for i in range(1, 65):
        cid = f"0905CS241{str(i).zfill(3)}"
        cur.execute(
            "INSERT OR IGNORE INTO students (college_id, password_hash, department) VALUES (?, ?, ?)",
            (cid, hash_password(f"{cid}#"), "Computer Science")
        )

    # Quick test student account
    cur.execute(
        "INSERT OR IGNORE INTO students (college_id, password_hash, department) VALUES (?, ?, ?)",
        ("STUDENT01", hash_password("vote123"), "Computer Science")
    )

    # Seed the 4 Stages of Elections if table is empty
    cur.execute("SELECT COUNT(*) FROM elections")
    if cur.fetchone()[0] == 0:
        now = datetime.now()
        end_time = (now + timedelta(hours=48)).isoformat()
        start_time = now.isoformat()

        # Stage 1: Class Election (CR)
        cur.execute("""
            INSERT INTO elections (name, stage, category_name, description, is_active, start_time, end_time)
            VALUES (?, 1, ?, ?, 1, ?, ?)
        """, (
            "Class Representative (CR) Election - CSE Year 3",
            "Class Election (CR)",
            "Elect your class representative. The winner directly advances to Step 2: Department Election!",
            start_time,
            end_time
        ))
        e1_id = cur.lastrowid
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto) VALUES (?, ?, ?, ?)",
                    (e1_id, "Aarav Sharma", "candidate1.png", "Passionate about lab equipment modernization and student advocacy."))
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto) VALUES (?, ?, ?, ?)",
                    (e1_id, "Priya Patel", "candidate2.png", "Promoting collaborative peer workshops and semester project support."))
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto) VALUES (?, ?, ?, ?)",
                    (e1_id, "Rohan Verma", "candidate3.png", "Focusing on transparent class communications and internship drives."))

        # Stage 2: Department Election
        cur.execute("""
            INSERT INTO elections (name, stage, category_name, description, is_active, start_time, end_time)
            VALUES (?, 2, ?, ?, 1, ?, ?)
        """, (
            "Departmental Representative - Faculty of Engineering",
            "Department Election",
            "Department-wide election. Candidates include promoted winners from respective class elections.",
            start_time,
            end_time
        ))
        e2_id = cur.lastrowid
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto, promoted_from_stage, promotion_status) VALUES (?, ?, ?, ?, ?, ?)",
                    (e2_id, "Neha Gupta", "candidate2.png", "Advanced from Class Section A. Standing for engineering curriculum enrichment.", 1, "Promoted from Class Election (CR)"))
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto) VALUES (?, ?, ?, ?)",
                    (e2_id, "Vikram Malhotra", "candidate1.png", "Focusing on inter-department hackathons and research grants."))

        # Stage 3: University Council
        cur.execute("""
            INSERT INTO elections (name, stage, category_name, description, is_active, start_time, end_time)
            VALUES (?, 3, ?, ?, 1, ?, ?)
        """, (
            "University Council - Student Body Executive Election",
            "University Council",
            "Apex student governing body representation. Open to all students campus-wide.",
            start_time,
            end_time
        ))
        e3_id = cur.lastrowid
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto, promoted_from_stage, promotion_status) VALUES (?, ?, ?, ?, ?, ?)",
                    (e3_id, "Kavita Rao", "candidate2.png", "Former Department Representative. Advocating for campus healthcare and student fee transparency.", 2, "Promoted from Department Election"))
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto) VALUES (?, ?, ?, ?)",
                    (e3_id, "Aditya Sen", "candidate3.png", "Leading university sports infrastructure and annual cultural symposium."))

        # Stage 4: Campus Policies & Committees
        cur.execute("""
            INSERT INTO elections (name, stage, category_name, description, is_active, start_time, end_time)
            VALUES (?, 4, ?, ?, 1, ?, ?)
        """, (
            "Campus Policy Referendum - 24/7 Digital Library & Ethics Committee",
            "Campus Policies & Committees",
            "Vote on proposed campus policy amendments, student life improvements, and committee representation.",
            start_time,
            end_time
        ))
        e4_id = cur.lastrowid
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto) VALUES (?, ?, ?, ?)",
                    (e4_id, "Option A: Approve 24/7 Library & Lab Access", "default.png", "Full approval with student security badge integration."))
        cur.execute("INSERT INTO candidates (election_id, name, photo, manifesto) VALUES (?, ?, ?, ?)",
                    (e4_id, "Option B: Approve with Extended Weekend Hours Only", "default.png", "Alternative plan optimizing weekend and exam week facilities."))

    conn.commit()
    conn.close()


# ---------------- HOME PAGE ----------------
@app.route("/")
@app.route("/home")
def home():
    expire_elections()
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM elections WHERE is_active=1 ORDER BY stage ASC, id ASC")
    active_elections = rows_to_dicts(cur.fetchall())
    conn.close()

    for e in active_elections:
        e["status"] = "Active"
        e["stage_info"] = STAGE_CONFIG.get(e["stage"], {})

    return render_template(
        "home.html",
        active_elections=active_elections,
        stages=STAGE_CONFIG
    )


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        cid = request.form.get("college_id", "").strip().upper()
        pwd = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        dept = request.form.get("department", "Computer Science").strip()

        if not cid or not pwd:
            flash("All fields are required", "danger")
            return redirect(url_for("register"))

        if pwd != confirm:
            flash("Passwords do not match", "danger")
            return redirect(url_for("register"))

        if len(pwd) < 6:
            flash("Password must be at least 6 characters long", "danger")
            return redirect(url_for("register"))

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM students WHERE college_id=?", (cid,))
        if cur.fetchone():
            flash("College ID already registered. Please log in.", "warning")
            conn.close()
            return redirect(url_for("login"))

        try:
            cur.execute(
                "INSERT INTO students (college_id, password_hash, department) VALUES (?, ?, ?)",
                (cid, hash_password(pwd), dept)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("College ID already registered", "danger")
            conn.close()
            return redirect(url_for("register"))

        conn.close()
        flash("Registration successful! You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        cid = request.form.get("college_id", "").strip().upper()
        pwd = request.form.get("password", "")

        conn = get_conn()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM students WHERE college_id=?", (cid,))
        student = row_to_dict(cur.fetchone())
        conn.close()

        if not student or not verify_password(student["password_hash"], pwd):
            flash("Invalid College ID or password", "danger")
            return redirect(url_for("login"))

        session.clear()
        session["student"] = {
            "id": student["id"],
            "college_id": cid,
            "department": student.get("department", "Computer Science")
        }
        return redirect(url_for("vote_hub"))

    return render_template("login.html")


# ---------------- MULTI-STAGE VOTING HUB ----------------
@app.route("/vote")
def vote_hub():
    if "student" not in session:
        return redirect(url_for("login"))

    expire_elections()
    sid = session["student"]["id"]

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM elections WHERE is_active=1 ORDER BY stage ASC, id ASC")
    elections = rows_to_dicts(cur.fetchall())

    cur.execute("SELECT election_id FROM votes WHERE student_id=?", (sid,))
    voted_elections = {r[0] for r in cur.fetchall()}
    conn.close()

    for e in elections:
        e["has_voted"] = e["id"] in voted_elections
        e["stage_info"] = STAGE_CONFIG.get(e["stage"], {})

    return render_template(
        "vote_hub.html",
        elections=elections,
        stages=STAGE_CONFIG,
        student=session["student"]
    )


# ---------------- VOTE IN SPECIFIC ELECTION ----------------
@app.route("/vote/<int:election_id>", methods=["GET", "POST"])
def vote(election_id):
    if "student" not in session:
        return redirect(url_for("login"))

    expire_elections()
    sid = session["student"]["id"]
    now = datetime.now().isoformat()

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM elections WHERE id=? AND is_active=1 AND start_time<=? AND end_time>=?",
                (election_id, now, now))
    election = row_to_dict(cur.fetchone())

    if not election:
        conn.close()
        flash("Election is not currently active or does not exist.", "warning")
        return redirect(url_for("vote_hub"))

    cur.execute("SELECT 1 FROM votes WHERE election_id=? AND student_id=?", (election["id"], sid))
    has_voted = cur.fetchone() is not None

    if request.method == "POST":
        if has_voted:
            conn.close()
            return redirect(url_for("thanks", election_id=election["id"]))

        candidate_id = request.form.get("candidate")
        if not candidate_id:
            conn.close()
            flash("Please select a candidate before casting your ballot.", "danger")
            return redirect(url_for("vote", election_id=election_id))

        try:
            cur.execute(
                "INSERT INTO votes (election_id, student_id, candidate_id) VALUES (?, ?, ?)",
                (election["id"], sid, candidate_id)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return redirect(url_for("thanks", election_id=election["id"]))

        conn.close()
        return redirect(url_for("thanks", election_id=election["id"]))

    cur.execute("SELECT * FROM candidates WHERE election_id=?", (election["id"],))
    candidates = rows_to_dicts(cur.fetchall())
    conn.close()

    election["stage_info"] = STAGE_CONFIG.get(election["stage"], {})

    return render_template(
        "vote.html",
        election=election,
        candidates=candidates,
        has_voted=has_voted,
        student=session["student"]
    )


# ---------------- THANKS ----------------
@app.route("/thanks")
@app.route("/thanks/<int:election_id>")
def thanks(election_id=None):
    return render_template("thanks.html", election_id=election_id)


# ---------------- RESULTS ----------------
@app.route("/results")
@app.route("/results/<int:election_id>")
def results(election_id=None):
    expire_elections()

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM elections ORDER BY stage ASC, id DESC")
    all_elections = rows_to_dicts(cur.fetchall())

    if not all_elections:
        conn.close()
        return render_template("results.html", status="no_election")

    if election_id:
        cur.execute("SELECT * FROM elections WHERE id=?", (election_id,))
        election = row_to_dict(cur.fetchone())
    else:
        # Default to first concluded election, or first election
        concluded = [e for e in all_elections if e["is_active"] == 0]
        election = concluded[0] if concluded else all_elections[0]

    if not election:
        conn.close()
        return render_template("results.html", status="no_election")

    election["stage_info"] = STAGE_CONFIG.get(election["stage"], {})

    if election["is_active"] == 1:
        conn.close()
        return render_template(
            "results.html",
            status="running",
            election=election,
            all_elections=all_elections,
            stages=STAGE_CONFIG
        )

    # Concluded election, compile candidate tallies
    cur.execute("""
        SELECT c.id, c.name, c.photo, c.manifesto, c.promoted_from_stage, c.promotion_status,
               COUNT(v.id) AS votes
        FROM candidates c
        LEFT JOIN votes v ON c.id=v.candidate_id
        WHERE c.election_id=?
        GROUP BY c.id
        ORDER BY votes DESC
    """, (election["id"],))
    results_list = rows_to_dicts(cur.fetchall())

    total_votes = sum(c["votes"] for c in results_list)
    for c in results_list:
        c["percent"] = round((c["votes"] / total_votes * 100), 1) if total_votes > 0 else 0

    winner = results_list[0] if results_list and results_list[0]["votes"] > 0 else (results_list[0] if results_list else None)

    conn.close()

    return render_template(
        "results.html",
        status="ended",
        election=election,
        all_elections=all_elections,
        results=results_list,
        winner=winner,
        total_votes=total_votes,
        stages=STAGE_CONFIG
    )


# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and "admin_login" in request.form:
        if request.form.get("password") == ADMIN_PASS:
            session.clear()
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Incorrect admin password", "danger")

    if "admin" not in session:
        return render_template("admin.html", logged_in=False)

    expire_elections()

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Create Election Handler
    if request.method == "POST" and "create_election" in request.form:
        try:
            duration = int(request.form.get("duration", 0))
            stage = int(request.form.get("stage", 1))
        except (ValueError, TypeError):
            flash("Invalid duration or stage", "danger")
            duration = None
            stage = 1

        election_name = request.form.get("election_name", "").strip()
        description = request.form.get("description", "").strip()
        category_name = STAGE_CONFIG.get(stage, {}).get("title", f"Stage {stage}")

        if election_name and duration and duration > 0:
            start = datetime.now()
            end = start + timedelta(minutes=duration)

            cur.execute("""
                INSERT INTO elections (name, stage, category_name, description, is_active, start_time, end_time)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (election_name, stage, category_name, description, start.isoformat(), end.isoformat()))
            conn.commit()
            flash(f"Election '{election_name}' created in [{category_name}]!", "success")
            return redirect(url_for("admin"))

    # Add Candidate Handler
    if request.method == "POST" and "add_candidate" in request.form:
        election_id = request.form.get("election_id")
        candidate_name = request.form.get("candidate_name", "").strip()
        manifesto = request.form.get("manifesto", "").strip()
        photo = request.files.get("photo")

        if not election_id or not candidate_name:
            flash("Election and Candidate Name are required", "danger")
        else:
            unique_name = "default.png"
            if photo and photo.filename != "":
                if allowed_file(photo.filename):
                    try:
                        image = Image.open(photo)
                        image.verify()
                        photo.seek(0)
                        filename = secure_filename(photo.filename)
                        base, ext = os.path.splitext(filename)
                        unique_name = f"{base}_{int(datetime.now().timestamp())}{ext}"
                        photo.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
                    except Exception:
                        unique_name = "default.png"

            cur.execute(
                "INSERT INTO candidates (election_id, name, photo, manifesto) VALUES (?, ?, ?, ?)",
                (election_id, candidate_name, unique_name, manifesto)
            )
            conn.commit()
            flash(f"Candidate '{candidate_name}' added successfully!", "success")
            return redirect(url_for("admin"))

    # End Election Handler
    if request.method == "POST" and "end_election_id" in request.form:
        eid = request.form.get("end_election_id")
        cur.execute("UPDATE elections SET is_active=0 WHERE id=?", (eid,))
        conn.commit()
        flash("Election concluded and final tallies published!", "info")
        return redirect(url_for("admin"))

    # Fetch elections list
    cur.execute("SELECT * FROM elections ORDER BY stage ASC, id DESC")
    all_elections = rows_to_dicts(cur.fetchall())

    cur.execute("SELECT COUNT(*) FROM students")
    total_students = cur.fetchone()[0]

    # Calculate overall stats
    cur.execute("SELECT COUNT(DISTINCT student_id) FROM votes")
    unique_voters = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM votes")
    total_votes_cast = cur.fetchone()[0]

    # Enhance elections with candidate counts and tallies
    for e in all_elections:
        e["stage_info"] = STAGE_CONFIG.get(e["stage"], {})
        cur.execute("""
            SELECT c.id, c.name, c.photo, c.manifesto, c.promoted_from_stage, c.promotion_status,
                   COUNT(v.id) AS votes
            FROM candidates c
            LEFT JOIN votes v ON c.id=v.candidate_id
            WHERE c.election_id=?
            GROUP BY c.id
            ORDER BY votes DESC
        """, (e["id"],))
        e["candidates"] = rows_to_dicts(cur.fetchall())
        e["winner"] = e["candidates"][0] if e["candidates"] else None
        cur.execute("SELECT COUNT(*) FROM votes WHERE election_id=?", (e["id"],))
        e["votes_count"] = cur.fetchone()[0]

    # Fetch enrolled students
    cur.execute("SELECT * FROM students ORDER BY college_id ASC")
    students = rows_to_dicts(cur.fetchall())

    conn.close()

    turnout_pct = round((unique_voters / total_students * 100), 1) if total_students > 0 else 0

    return render_template(
        "admin.html",
        logged_in=True,
        elections=all_elections,
        students=students,
        total_students=total_students,
        unique_voters=unique_voters,
        total_votes_cast=total_votes_cast,
        turnout_pct=turnout_pct,
        stages=STAGE_CONFIG
    )


# ---------------- PROMOTION TO NEXT ROUND (CR -> DEPT -> COUNCIL) ----------------
@app.route("/admin/promote_candidate", methods=["POST"])
def promote_candidate():
    if "admin" not in session:
        return redirect(url_for("admin"))

    source_candidate_id = request.form.get("candidate_id")
    target_election_id = request.form.get("target_election_id")

    if not source_candidate_id or not target_election_id:
        flash("Source candidate and target election must be specified.", "danger")
        return redirect(url_for("admin"))

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT c.*, e.stage, e.name as election_name
        FROM candidates c
        JOIN elections e ON c.election_id = e.id
        WHERE c.id=?
    """, (source_candidate_id,))
    candidate = row_to_dict(cur.fetchone())

    cur.execute("SELECT * FROM elections WHERE id=?", (target_election_id,))
    target_election = row_to_dict(cur.fetchone())

    if not candidate or not target_election:
        conn.close()
        flash("Candidate or target round not found.", "danger")
        return redirect(url_for("admin"))

    # Check if candidate is already in the target election
    cur.execute("SELECT id FROM candidates WHERE election_id=? AND name=?",
                (target_election["id"], candidate["name"]))
    if cur.fetchone():
        conn.close()
        flash(f"Candidate '{candidate['name']}' is already competing in '{target_election['name']}'.", "warning")
        return redirect(url_for("admin"))

    promotion_tag = f"Promoted Winner from {candidate['election_name']}"

    cur.execute("""
        INSERT INTO candidates (election_id, name, photo, manifesto, promoted_from_stage, promotion_status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        target_election["id"],
        candidate["name"],
        candidate["photo"] or "default.png",
        candidate["manifesto"] or "Promoted to next round.",
        candidate["stage"],
        promotion_tag
    ))
    conn.commit()
    conn.close()

    flash(f"🎉 Success! '{candidate['name']}' has been officially promoted to '{target_election['name']}'!", "success")
    return redirect(url_for("admin"))


# ---------------- DELETE CANDIDATE ----------------
@app.route("/delete_candidate/<int:cid>", methods=["POST"])
def delete_candidate(cid):
    if "admin" not in session:
        return redirect(url_for("admin"))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM votes WHERE candidate_id=?", (cid,))
    cur.execute("DELETE FROM candidates WHERE id=?", (cid,))
    conn.commit()
    conn.close()

    flash("Candidate removed successfully.", "success")
    return redirect(url_for("admin"))


# ---------------- DELETE STUDENT ----------------
@app.route("/delete_student/<college_id>", methods=["POST"])
def delete_student(college_id):
    if "admin" not in session:
        return redirect(url_for("admin"))

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM students WHERE college_id=?", (college_id,))
    row = cur.fetchone()

    if row:
        cur.execute("DELETE FROM votes WHERE student_id=?", (row[0],))
        cur.execute("DELETE FROM students WHERE id=?", (row[0],))
        conn.commit()
        flash(f"Student record '{college_id}' deleted.", "success")

    conn.close()
    return redirect(url_for("admin"))


# ---------------- MAIN ----------------
if __name__ == "__main__":
    init_db()
    seed_data()
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    print("=====================================================")
    print(" VoteEase Multi-Stage College Voting System")
    print(" Live Server: http://127.0.0.1:5000")
    print(" Admin Portal: http://127.0.0.1:5000/admin (Key: admin123)")
    print(" Demo Student: STUDENT01 (Pass: vote123)")
    print("=====================================================")
    app.run(host="127.0.0.1", port=5000, debug=debug_mode)
