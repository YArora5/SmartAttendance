import cv2
import os

student_id = input("Enter Student ID (digits only): ").strip()
if not student_id.isdigit():
    raise SystemExit("Student ID must contain digits only.")

dataset_path = os.path.join("dataset", student_id)
os.makedirs(dataset_path, exist_ok=True)

cam = cv2.VideoCapture(0)
if not cam.isOpened():
    raise SystemExit("Could not open webcam. Check camera permissions and connection.")

face_detector = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
if face_detector.empty():
    cam.release()
    raise SystemExit("Could not load the OpenCV face detector.")

count = 0

while True:
    ret, frame = cam.read()
    if not ret or frame is None:
        print("Could not read a frame from the webcam.")
        break
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_detector.detectMultiScale(gray, 1.3, 5)

    for (x,y,w,h) in faces:
        count += 1
        cv2.imwrite(
            f"{dataset_path}/{count}.jpg",
            gray[y:y+h, x:x+w]
        )
        cv2.rectangle(frame,(x,y),(x+w,y+h),(255,0,0),2)

    cv2.imshow("Capturing Faces", frame)

    if cv2.waitKey(1) == 27 or count >= 30:
        break

cam.release()
cv2.destroyAllWindows()
print("Dataset created successfully!")
