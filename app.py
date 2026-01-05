from flask import Flask, render_template, request, redirect, session, send_from_directory
import sqlite3, json, os, random, datetime

try:
    import cv2
except:
    cv2 = None

app = Flask(__name__)
app.secret_key = "college_secret_key"

# ================= FOLDERS =================
os.makedirs("uploads", exist_ok=True)
os.makedirs("notes", exist_ok=True)
os.makedirs("model", exist_ok=True)

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            date TEXT,
            time TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ================= JSON HELPERS =================
def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f)
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

# ================= ROOT =================
@app.route("/")
def home():
    return redirect("/login/student")

# ================= STUDENT LOGIN =================
@app.route("/login/student", methods=["GET","POST"])
def login_student():
    if request.method == "POST":
        sid = request.form["student_id"]
        students = load_json("student_data.json", {})
        if sid in students:
            session.clear()
            session["student"] = sid
            return redirect("/student/dashboard")
        return render_template("login_student.html", error="Invalid Student ID")
    return render_template("login_student.html")

# ================= STUDENT DASHBOARD =================
@app.route("/student/dashboard")
def student_dashboard():
    if "student" not in session:
        return redirect("/login/student")

    sid = session["student"]
    students = load_json("student_data.json", {})
    student = students.get(sid)

    today = datetime.date.today().strftime("%Y-%m-%d")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_id=? AND date=?", (sid,today))
    present = c.fetchone()[0]
    conn.close()

    status = "Present ✅" if present else "Absent ❌"

    return render_template("dashboard_student.html",
        student=student,
        today_status=status
    )

@app.route("/student/attendance")
def student_attendance():
    if "student" not in session:
        return redirect("/login/student")

    sid = session["student"]
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT date,time FROM attendance WHERE student_id=?", (sid,))
    rows = c.fetchall()
    conn.close()

    return render_template("student_attendance.html", attendance=rows)

@app.route("/routine")
def routine():
    return render_template("routine.html")

@app.route("/activity")
def activity():
    return render_template("activity.html",
        activity=random.choice([
            "Revise notes",
            "Practice coding",
            "Read textbook",
            "Watch lecture video"
        ])
    )

@app.route("/notes")
def notes():
    files = os.listdir("notes")
    return render_template("notes.html", files=files)

@app.route("/announcements")
def announcements():
    data = load_json("announcements.json", [])
    return render_template("announcements.html", announcements=data)

@app.route("/curriculum")
def curriculum():
    syllabus = load_json("syllabus.json", {})
    return render_template("curriculum.html", syllabus=syllabus)

# ================= TEACHER LOGIN =================
@app.route("/login/teacher", methods=["GET","POST"])
def login_teacher():
    if request.method == "POST":
        if request.form["username"]=="admin" and request.form["password"]=="1234":
            session.clear()
            session["teacher"] = True
            return redirect("/teacher/dashboard")
        return render_template("login_teacher.html", error="Invalid Login")
    return render_template("login_teacher.html")

# ================= TEACHER DASHBOARD =================
@app.route("/teacher/dashboard")
def teacher_dashboard():
    if "teacher" not in session:
        return redirect("/login/teacher")
    return render_template("dashboard_teacher.html")

# ================= FACE ATTENDANCE =================
@app.route("/mark-attendance")
def mark_attendance():
    if "teacher" not in session:
        return redirect("/login/teacher")

    if cv2 is None or not os.path.exists("model/face_model.xml"):
        return "Face model not found"

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read("model/face_model.xml")

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cam = cv2.VideoCapture(0)

    while True:
        ret, frame = cam.read()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray,1.3,5)

        for (x,y,w,h) in faces:
            label, _ = recognizer.predict(gray[y:y+h, x:x+w])

            now = datetime.datetime.now()
            conn = sqlite3.connect("attendance.db")
            c = conn.cursor()
            c.execute(
                "INSERT INTO attendance(student_id,date,time) VALUES(?,?,?)",
                (str(label), now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"))
            )
            conn.commit()
            conn.close()

            cam.release()
            cv2.destroyAllWindows()
            return redirect("/teacher/dashboard")

        cv2.imshow("Face Attendance", frame)
        if cv2.waitKey(1) == 13:
            break

    cam.release()
    cv2.destroyAllWindows()
    return redirect("/teacher/dashboard")

# ================= TEACHER EXTRA =================
@app.route("/teacher/monthly-graph")
def teacher_monthly_graph():
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT date FROM attendance")
    rows = c.fetchall()
    conn.close()

    months = {}
    for (d,) in rows:
        m = d[:7]
        months[m] = months.get(m,0)+1

    return render_template("monthly_graph.html",
        bar_labels=list(months.keys()),
        bar_values=list(months.values())
    )

@app.route("/upload-syllabus", methods=["GET","POST"])
def upload_syllabus():
    if request.method=="POST":
        sub = request.form["subject"]
        file = request.files["file"]
        file.save("uploads/"+file.filename)

        data = load_json("syllabus.json",{})
        data[sub] = file.filename
        save_json("syllabus.json",data)

        return redirect("/curriculum")
    return render_template("upload_syllabus.html")

@app.route("/teacher/upload-notes", methods=["GET","POST"])
def upload_notes():
    if request.method=="POST":
        file = request.files["file"]
        file.save("notes/"+file.filename)
        return redirect("/teacher/dashboard")
    return render_template("upload_notes.html")

@app.route("/teacher/add-announcement", methods=["GET","POST"])
def add_announcement():
    if request.method=="POST":
        data = load_json("announcements.json",[])
        data.append({
            "title": request.form["title"],
            "description": request.form["description"],
            "date": str(datetime.date.today())
        })
        save_json("announcements.json",data)
        return redirect("/teacher/dashboard")
    return render_template("add_announcement.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login/student")

@app.route("/view-pdf/<name>")
def view_pdf(name):
    if os.path.exists("uploads/"+name):
        return send_from_directory("uploads",name)
    if os.path.exists("notes/"+name):
        return send_from_directory("notes",name)
    return "File not found",404

if __name__ == "__main__":
    app.run(debug=True)
