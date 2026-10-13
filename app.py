
import os
import json
import random
import sqlite3
import datetime
from functools import wraps
from pathlib import Path

import cv2
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    send_from_directory,
    abort,
    url_for,
)
from werkzeug.utils import secure_filename


# =========================================================
# PATHS AND CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = BASE_DIR / "uploads"
NOTES_FOLDER = BASE_DIR / "notes"
MODEL_FOLDER = BASE_DIR / "model"

DATABASE = BASE_DIR / "attendance.db"
STUDENT_DATA_FILE = BASE_DIR / "student_data.json"
ANNOUNCEMENTS_FILE = BASE_DIR / "announcements.json"
SYLLABUS_FILE = BASE_DIR / "syllabus.json"

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("COOKIE_SECURE", "0") == "1"
)

secret_key = os.environ.get("FLASK_SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is missing. "
        "Set it as an environment variable before starting the app."
    )

app.secret_key = secret_key

TEACHER_USERNAME = os.environ.get("TEACHER_USERNAME")
TEACHER_PASSWORD = os.environ.get("TEACHER_PASSWORD")

ALLOWED_EXTENSIONS = {"pdf"}

# LBPH confidence is a distance: lower is generally a closer match.
# This is a configurable starting value, NOT a validated security threshold.
try:
    FACE_CONFIDENCE_THRESHOLD = float(
        os.environ.get("FACE_CONFIDENCE_THRESHOLD", "50")
    )
except ValueError as exc:
    raise RuntimeError(
        "FACE_CONFIDENCE_THRESHOLD must be a number."
    ) from exc

if FACE_CONFIDENCE_THRESHOLD <= 0:
    raise RuntimeError(
        "FACE_CONFIDENCE_THRESHOLD must be greater than zero."
    )

for folder in (UPLOAD_FOLDER, NOTES_FOLDER, MODEL_FOLDER):
    folder.mkdir(parents=True, exist_ok=True)


# =========================================================
# DATABASE
# =========================================================

def get_db():
    connection = sqlite3.connect(str(DATABASE), timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL
            )
        """)

        # Prevent multiple attendance records for the same student
        # on the same date. Existing duplicate rows must be reviewed
        # and cleaned up before this index can be created.
        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            unique_student_attendance_per_day
            ON attendance(student_id, date)
        """)


init_db()


# =========================================================
# JSON HELPERS
# =========================================================

def load_json(file_path, default):
    if not file_path.exists():
        return default

    try:
        with file_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        app.logger.exception(
            "Failed to read JSON file: %s",
            file_path.name,
        )
        abort(500, description="A data file could not be read.")


def save_json(file_path, data):
    try:
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False,
            )
    except OSError:
        app.logger.exception(
            "Failed to write JSON file: %s",
            file_path.name,
        )
        abort(500, description="Data could not be saved.")


def allowed_file(filename):
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def get_students():
    students = load_json(STUDENT_DATA_FILE, {})

    if not isinstance(students, dict):
        app.logger.error("student_data.json must contain a JSON object.")
        abort(500, description="Student data has an invalid format.")

    return students


def get_announcements():
    data = load_json(ANNOUNCEMENTS_FILE, [])

    if not isinstance(data, list):
        abort(500, description="Announcement data has an invalid format.")

    return data


def get_syllabus():
    data = load_json(SYLLABUS_FILE, {})

    if not isinstance(data, dict):
        abort(500, description="Syllabus data has an invalid format.")

    return data


# =========================================================
# ACCESS CONTROL
# =========================================================

def student_required(view_function):
    @wraps(view_function)
    def wrapped(*args, **kwargs):
        if "student" not in session:
            return redirect(url_for("login_student"))

        return view_function(*args, **kwargs)

    return wrapped


def teacher_required(view_function):
    @wraps(view_function)
    def wrapped(*args, **kwargs):
        if session.get("teacher") is not True:
            return redirect(url_for("login_teacher"))

        return view_function(*args, **kwargs)

    return wrapped


def logged_in_required(view_function):
    @wraps(view_function)
    def wrapped(*args, **kwargs):
        is_student = "student" in session
        is_teacher = session.get("teacher") is True

        if not is_student and not is_teacher:
            abort(403)

        return view_function(*args, **kwargs)

    return wrapped


# =========================================================
# ROOT
# =========================================================

@app.route("/")
def home():
    if session.get("teacher") is True:
        return redirect(url_for("teacher_dashboard"))

    if "student" in session:
        return redirect(url_for("student_dashboard"))

    return redirect(url_for("login_student"))


# =========================================================
# STUDENT LOGIN
# =========================================================

@app.route("/login/student", methods=["GET", "POST"])
def login_student():
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        students = get_students()

        if student_id and student_id in students:
            session.clear()
            session["student"] = student_id
            return redirect(url_for("student_dashboard"))

        return render_template(
            "login_student.html",
            error="Invalid Student ID",
        )

    return render_template("login_student.html")


# =========================================================
# STUDENT DASHBOARD
# =========================================================

@app.route("/student/dashboard")
@student_required
def student_dashboard():
    student_id = session["student"]
    students = get_students()
    student = students.get(student_id)

    if student is None:
        session.clear()
        return redirect(url_for("login_student"))

    today = datetime.date.today().isoformat()

    with get_db() as connection:
        result = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM attendance
            WHERE student_id = ? AND date = ?
            """,
            (student_id, today),
        ).fetchone()

    today_status = (
        "Present ✅" if result["total"] > 0 else "Absent ❌"
    )

    return render_template(
        "dashboard_student.html",
        student=student,
        today_status=today_status,
    )


@app.route("/student/attendance")
@student_required
def student_attendance():
    student_id = session["student"]

    with get_db() as connection:
        records = connection.execute(
            """
            SELECT date, time
            FROM attendance
            WHERE student_id = ?
            ORDER BY date DESC, time DESC
            """,
            (student_id,),
        ).fetchall()

    return render_template(
        "student_attendance.html",
        attendance=records,
    )


# =========================================================
# STUDENT PAGES
# =========================================================

@app.route("/routine")
@student_required
def routine():
    return render_template("routine.html")


@app.route("/activity")
@student_required
def activity():
    suggested_activity = random.choice([
        "Revise notes",
        "Practice coding",
        "Read textbook",
        "Watch lecture video",
    ])

    return render_template(
        "activity.html",
        activity=suggested_activity,
    )


@app.route("/notes")
@student_required
def notes():
    files = sorted(
        item.name
        for item in NOTES_FOLDER.iterdir()
        if item.is_file() and item.suffix.lower() == ".pdf"
    )

    return render_template("notes.html", files=files)


@app.route("/announcements")
@student_required
def announcements():
    return render_template(
        "announcements.html",
        announcements=get_announcements(),
    )


@app.route("/curriculum")
@student_required
def curriculum():
    return render_template(
        "curriculum.html",
        syllabus=get_syllabus(),
    )


# =========================================================
# TEACHER LOGIN
# =========================================================

@app.route("/login/teacher", methods=["GET", "POST"])
def login_teacher():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        credentials_configured = bool(
            TEACHER_USERNAME and TEACHER_PASSWORD
        )

        if (
            credentials_configured
            and username == TEACHER_USERNAME
            and password == TEACHER_PASSWORD
        ):
            session.clear()
            session["teacher"] = True
            return redirect(url_for("teacher_dashboard"))

        return render_template(
            "login_teacher.html",
            error="Invalid Login",
        )

    return render_template("login_teacher.html")


# =========================================================
# TEACHER DASHBOARD
# =========================================================

@app.route("/teacher/dashboard")
@teacher_required
def teacher_dashboard():
    return render_template("dashboard_teacher.html")


# =========================================================
# FACE ATTENDANCE
# =========================================================

@app.route("/mark-attendance", methods=["GET", "POST"])
@teacher_required
def mark_attendance():
    model_file = MODEL_FOLDER / "face_model.xml"

    if not hasattr(cv2, "face"):
        return (
            "Face recognition is unavailable. Install "
            "opencv-contrib-python in the active environment.",
            503,
        )

    if not model_file.is_file():
        return "Face model not found. Train the model first.", 404

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(str(model_file))
    except cv2.error:
        app.logger.exception("Could not load the face model.")
        return "The face model could not be loaded.", 500

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades
        + "haarcascade_frontalface_default.xml"
    )

    if face_cascade.empty():
        return "Face detector could not be loaded.", 500

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        camera.release()
        return "Camera could not be opened.", 503

    try:
        while True:
            success, frame = camera.read()

            if not success or frame is None:
                return "Could not read from the camera.", 503

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.3,
                minNeighbors=5,
            )

            for (x, y, width, height) in faces:
                face_image = gray[
                    y:y + height,
                    x:x + width,
                ]

                label, confidence = recognizer.predict(face_image)

                # LBPH confidence is a distance. A lower value
                # generally indicates a closer match. The threshold
                # must be validated with representative test images.
                if confidence > FACE_CONFIDENCE_THRESHOLD:
                    continue

                student_id = str(label)

                # The training labels must correspond to student IDs
                # in student_data.json. Reject unknown labels.
                students = get_students()

                if student_id not in students:
                    app.logger.warning(
                        "Model returned an unknown student label."
                    )
                    continue

                today = datetime.date.today().isoformat()
                current_time = datetime.datetime.now().strftime(
                    "%H:%M:%S"
                )

                try:
                    with get_db() as connection:
                        connection.execute(
                            """
                            INSERT INTO attendance
                                (student_id, date, time)
                            VALUES (?, ?, ?)
                            ON CONFLICT(student_id, date) DO NOTHING
                            """,
                            (student_id, today, current_time),
                        )
                except sqlite3.Error:
                    app.logger.exception(
                        "Could not record attendance."
                    )
                    return "Attendance could not be recorded.", 500

                return redirect(url_for("teacher_dashboard"))

            cv2.imshow("Face Attendance", frame)

            # Press Enter to stop scanning.
            if cv2.waitKey(1) & 0xFF == 13:
                break

    except cv2.error:
        app.logger.exception("Camera or recognition failure.")
        return "Face attendance failed. Check the camera and model.", 500

    finally:
        camera.release()
        cv2.destroyAllWindows()

    return redirect(url_for("teacher_dashboard"))


# =========================================================
# TEACHER MONTHLY GRAPH
# =========================================================

@app.route("/teacher/monthly-graph")
@teacher_required
def teacher_monthly_graph():
    with get_db() as connection:
        rows = connection.execute(
            "SELECT date FROM attendance ORDER BY date"
        ).fetchall()

    months = {}

    for row in rows:
        month = row["date"][:7]
        months[month] = months.get(month, 0) + 1

    return render_template(
        "monthly_graph.html",
        bar_labels=list(months.keys()),
        bar_values=list(months.values()),
    )


# =========================================================
# SYLLABUS UPLOAD
# =========================================================

@app.route("/upload-syllabus", methods=["GET", "POST"])
@teacher_required
def upload_syllabus():
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        uploaded_file = request.files.get("file")

        if (
            not subject
            or uploaded_file is None
            or not uploaded_file.filename
        ):
            abort(
                400,
                description="Subject and PDF file are required.",
            )

        if not allowed_file(uploaded_file.filename):
            abort(400, description="Only PDF files are allowed.")

        filename = secure_filename(uploaded_file.filename)

        if not filename:
            abort(400, description="Invalid filename.")

        # Prefix filenames to reduce accidental overwriting.
        stored_name = (
            datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
            + "_"
            + filename
        )

        uploaded_file.save(str(UPLOAD_FOLDER / stored_name))

        syllabus = get_syllabus()
        syllabus[subject] = stored_name
        save_json(SYLLABUS_FILE, syllabus)

        return redirect(url_for("curriculum"))

    return render_template("upload_syllabus.html")


# =========================================================
# NOTES UPLOAD
# =========================================================

@app.route("/teacher/upload-notes", methods=["GET", "POST"])
@teacher_required
def upload_notes():
    if request.method == "POST":
        uploaded_file = request.files.get("file")

        if uploaded_file is None or not uploaded_file.filename:
            abort(400, description="Please select a PDF file.")

        if not allowed_file(uploaded_file.filename):
            abort(400, description="Only PDF files are allowed.")

        filename = secure_filename(uploaded_file.filename)

        if not filename:
            abort(400, description="Invalid filename.")

        stored_name = (
            datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
            + "_"
            + filename
        )

        uploaded_file.save(str(NOTES_FOLDER / stored_name))

        return redirect(url_for("teacher_dashboard"))

    return render_template("upload_notes.html")


# =========================================================
# ADD ANNOUNCEMENT
# =========================================================

@app.route(
    "/teacher/add-announcement",
    methods=["GET", "POST"],
)
@teacher_required
def add_announcement():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        if not title or not description:
            abort(
                400,
                description="Title and description are required.",
            )

        data = get_announcements()

        data.append({
            "title": title,
            "description": description,
            "date": datetime.date.today().isoformat(),
        })

        save_json(ANNOUNCEMENTS_FILE, data)

        return redirect(url_for("teacher_dashboard"))

    return render_template("add_announcement.html")


# =========================================================
# FILE VIEWING
# =========================================================

@app.route("/view-pdf/<path:name>")
@logged_in_required
def view_pdf(name):
    # Permit only a simple filename, never a nested path.
    if not name or secure_filename(name) != name:
        abort(404)

    if not allowed_file(name):
        abort(404)

    for folder in (UPLOAD_FOLDER, NOTES_FOLDER):
        file_path = folder / name

        if file_path.is_file():
            return send_from_directory(
                str(folder),
                name,
                mimetype="application/pdf",
                as_attachment=False,
            )

    abort(404)


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login_student"))


# =========================================================
# ERROR HANDLING
# =========================================================

@app.errorhandler(413)
def file_too_large(error):
    return "Upload too large. Maximum size is 10 MB.", 413


# =========================================================
# APPLICATION START
# =========================================================

if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
