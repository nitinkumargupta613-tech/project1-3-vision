import cv2
import mediapipe as mp
import numpy as np
import serial
import time
import platform
import requests
import threading
# ESP32 CONNECTION

ESP32_PORT = "COM5"
BAUD_RATE = 115200

try:
    esp32 = serial.Serial(
        ESP32_PORT,
        BAUD_RATE,
        timeout=1
    )

    time.sleep(2)

    print("ESP32 connected!")

except Exception as e:
    print("ESP32 connection error:")
    print(e)
    exit()

# MEDIAPIPE

mp_face_mesh = mp.solutions.face_mesh

face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# EYE LANDMARKS

LEFT_EYE = [362, 385, 387, 263, 373, 380]

RIGHT_EYE = [33, 160, 158, 133, 153, 144]

# EAR CALCULATION

def calculate_ear(landmarks, points):

    p1 = np.array([
        landmarks[points[0]].x,
        landmarks[points[0]].y
    ])

    p2 = np.array([
        landmarks[points[1]].x,
        landmarks[points[1]].y
    ])

    p3 = np.array([
        landmarks[points[2]].x,
        landmarks[points[2]].y
    ])

    p4 = np.array([
        landmarks[points[3]].x,
        landmarks[points[3]].y
    ])

    p5 = np.array([
        landmarks[points[4]].x,
        landmarks[points[4]].y
    ])

    p6 = np.array([
        landmarks[points[5]].x,
        landmarks[points[5]].y
    ])

    vertical1 = np.linalg.norm(p2 - p6)
    vertical2 = np.linalg.norm(p3 - p5)

    horizontal = np.linalg.norm(p1 - p4)

    return (vertical1 + vertical2) / (2.0 * horizontal)

# SETTINGS

EAR_THRESHOLD = 0.21

# More than 10 seconds
CLOSED_TIME = 10.0

# VARIABLES

eyes_closed_start = None

# IMPORTANT:
# Once True, it NEVER becomes False during this program.
drowsiness_detected = False

# CAMERA

cap = cv2.VideoCapture(0)

if not cap.isOpened():

    print("Camera could not be opened!")

    esp32.close()

    exit()


print("----------------------------------------")
print("DRIVER DROWSINESS DETECTION")
print("----------------------------------------")
print("Eyes must remain closed for MORE THAN 10 seconds.")
print("After detection, alarm will remain ON.")
print("Press Q to quit.")
print("----------------------------------------")

# MAIN LOOP

while True:

    ret, frame = cap.read()

    if not ret:
        break


    # Mirror camera
    frame = cv2.flip(frame, 1)


    # Convert BGR → RGB
    rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )


    # Process face
    results = face_mesh.process(rgb)

    current_time = time.time()

    # IF DROWSINESS HAS NOT YET BEEN DETECTED

    if not drowsiness_detected:

        if results.multi_face_landmarks:

            face_landmarks = results.multi_face_landmarks[0]

            landmarks = face_landmarks.landmark


            # Calculate EAR
            left_ear = calculate_ear(
                landmarks,
                LEFT_EYE
            )

            right_ear = calculate_ear(
                landmarks,
                RIGHT_EYE
            )

            ear = (left_ear + right_ear) / 2.0

            # EYES CLOSED

            if ear < EAR_THRESHOLD:

                if eyes_closed_start is None:

                    eyes_closed_start = current_time


                closed_duration = (
                    current_time - eyes_closed_start
                )


                # Display timer
                cv2.putText(
                    frame,
                    f"Eyes Closed: {closed_duration:.1f}s",
                    (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2
                )

                # MORE THAN 10 SECONDS

                if closed_duration > CLOSED_TIME:

                    print("================================")
                    print("DROWSINESS DETECTED!")
                    print("================================")


                    # IMPORTANT:
                    # This is never changed back to False.
                    drowsiness_detected = True


                    # Tell ESP32 to stop servo,
                    # turn LED ON and start buzzer.
                    esp32.write(b'D')

            # EYES OPEN

            else:

                eyes_closed_start = None

                cv2.putText(
                    frame,
                    "AWAKE",
                    (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 0),
                    2
                )


            # Display EAR
            cv2.putText(
                frame,
                f"EAR: {ear:.2f}",
                (20, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )


        else:

            cv2.putText(
                frame,
                "FACE NOT DETECTED",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2
            )


            eyes_closed_start = None

    # DROWSINESS DETECTED - PERMANENT STATE

    else:

        # Large warning on camera
        cv2.putText(
            frame,
            "DROWSINESS DETECTED",
            (20, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            3
        )


        cv2.putText(
            frame,
            "WAKE UP!",
            (20, 115),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255),
            3
        )


        cv2.putText(
            frame,
            "SYSTEM LOCKED",
            (20, 155),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )

    # SHOW CAMERA

    cv2.imshow(
        "Driver Drowsiness Detection",
        frame
    )

    # QUIT
  
    if cv2.waitKey(1) & 0xFF == ord('q'):

        break

# CLEANUP

cap.release()

cv2.destroyAllWindows()

face_mesh.close()

esp32.close()

print("Program stopped.")