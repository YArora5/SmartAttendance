# SmartAttendance

A student project exploring a Flask-based attendance portal with student and teacher views, attendance history, announcements, notes, syllabus uploads, and an OpenCV/LBPH face-recognition prototype.

## Status

This is an educational prototype, not a production-ready attendance or biometric system. It has not been independently security-audited. Do not use real student records or biometric data until authentication, authorization, privacy, retention, and deployment controls have been reviewed.

## Requirements

- Python 3.10+
- A local webcam for the face-attendance route
- The OpenCV contrib package for `cv2.face`

## Run locally

1. Create a virtual environment.
2. Install dependencies: `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set a long random `FLASK_SECRET_KEY`, `TEACHER_USERNAME`, and `TEACHER_PASSWORD`.
4. Add your own local student data and face dataset; do not commit personal records or face images.
5. Train the model with `python train_model.py` after adding valid grayscale face images under `dataset/<student_id>/`.
6. Run `python app.py` for local development only.

The app now requires a configured Flask secret and teacher credentials. Never deploy with Flask debug mode enabled or with example credentials.

## Security and data notes

- The SQLite database, local datasets, uploads, notes, and `.env` are local-only and should not be committed.
- Use synthetic/sample records only in a public demo.
- The current face-recognition approach is a prototype and needs liveness, false-match testing, access control, audit logging, and a privacy review before real-world use.
- File upload restrictions and route authorization still need broader testing before production deployment.

## Main files

- `app.py` — Flask routes and attendance workflows
- `capture_faces.py` — capture training samples
- `train_model.py` — train the LBPH face recognizer
- `templates/` and `static/` — UI templates and styles
