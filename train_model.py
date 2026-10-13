import cv2
import numpy as np
import os

dataset_path = "dataset"
if not os.path.isdir(dataset_path):
    raise SystemExit("Dataset folder not found. Capture face samples first.")

recognizer = cv2.face.LBPHFaceRecognizer_create()
faces = []
labels = []

for student_id in os.listdir(dataset_path):
    student_path = os.path.join(dataset_path, student_id)
    if not student_id.isdigit() or not os.path.isdir(student_path):
        continue
    for image_name in os.listdir(student_path):
        image_path = os.path.join(student_path, image_name)
        gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            print(f"Skipping unreadable image: {image_path}")
            continue
        faces.append(gray)
        labels.append(int(student_id))

if not faces:
    raise SystemExit("No valid face images found. Capture samples before training.")

os.makedirs("model", exist_ok=True)
recognizer.train(faces, np.array(labels, dtype=np.int32))
recognizer.save("model/face_model.xml")
print(f"Model trained with {len(faces)} images across {len(set(labels))} student IDs.")
