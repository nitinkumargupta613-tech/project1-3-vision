import cv2
import numpy as np
import serial
import time
import platform
import requests
import threading


# =========================================================
# ESP32 SETTINGS
# =========================================================

ESP32_PORT = "COM5"
BAUD_RATE = 115200

esp32 = None
esp32_lock = threading.Lock()


# =========================================================
# CONNECT TO ESP32
# =========================================================

def connect_esp32():
    global esp32

    try:
        esp32 = serial.Serial(
            ESP32_PORT,
            BAUD_RATE,
            timeout=0.1
        )

        # Give ESP32 time after opening serial
        time.sleep(2)

        # Clear old buffered data
        esp32.reset_input_buffer()
        esp32.reset_output_buffer()

        print("ESP32 connected!")
        return True

    except Exception as e:
        esp32 = None
        print("ESP32 not connected - Camera only mode.")
        print("ESP32 ERROR:", e)
        return False


connect_esp32()


# =========================================================
# SAFE ESP32 SEND
# =========================================================

def send_to_esp32(command):
    """
    Send one command to ESP32 safely.

    command:
        '1' = camera fire
        '0' = camera fire cleared
    """

    global esp32

    if esp32 is None:
        print(f"ESP32 unavailable - cannot send {command}")
        return False

    try:
        with esp32_lock:

            if not esp32.is_open:
                print("ESP32 serial port is closed.")
                return False

            esp32.write(command.encode("ascii"))
            esp32.flush()

        print(f"ESP32 SENT: {command}")
        return True

    except Exception as e:
        print("ESP32 WRITE ERROR:", e)
        return False


# =========================================================
# TELEGRAM SETTINGS
# =========================================================
#
# IMPORTANT:
# Do NOT put your real bot token in code that you share.
# Your old token was exposed in the previous pasted code,
# so regenerate it through BotFather and put the NEW token here.
#

TELEGRAM_BOT_TOKEN = "YOUR_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"


telegram_camera_sent = False
telegram_mq2_sent = False

telegram_lock = threading.Lock()


# =========================================================
# TELEGRAM FUNCTION
# =========================================================

def send_telegram_alert(message, frame=None):
    """
    Sends Telegram alert in a background thread.

    This function must NOT block the OpenCV camera loop.
    """

    try:

        # -------------------------------------------------
        # PHOTO ALERT
        # -------------------------------------------------

        if frame is not None:

            success, buffer = cv2.imencode(
                ".jpg",
                frame
            )

            if success:

                url = (
                    f"https://api.telegram.org/bot"
                    f"{TELEGRAM_BOT_TOKEN}/sendPhoto"
                )

                files = {
                    "photo": (
                        "fire_detected.jpg",
                        buffer.tobytes(),
                        "image/jpeg"
                    )
                }

                data = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": message
                }

                response = requests.post(
                    url,
                    data=data,
                    files=files,
                    timeout=10
                )

                print(
                    "Telegram response:",
                    response.text
                )

                return

        # -------------------------------------------------
        # TEXT ONLY FALLBACK
        # -------------------------------------------------

        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage"
        )

        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }

        response = requests.post(
            url,
            data=data,
            timeout=10
        )

        print(
            "Telegram response:",
            response.text
        )

    except Exception as e:

        print(
            "TELEGRAM ERROR:",
            e
        )


# =========================================================
# RUN TELEGRAM IN BACKGROUND
# =========================================================

def send_telegram_background(message, frame=None):
    """
    Starts Telegram request in a daemon thread.
    Camera processing continues immediately.
    """

    if frame is not None:
        frame = frame.copy()

    thread = threading.Thread(
        target=send_telegram_alert,
        args=(message, frame),
        daemon=True
    )

    thread.start()


# =========================================================
# MQ2 STATUS
# =========================================================

mq2_fire = False
mq2_raw = None
mq2_serial_buffer = ""


# =========================================================
# READ ESP32 STATUS
# =========================================================

def read_esp32_status():

    global mq2_fire
    global mq2_raw
    global mq2_serial_buffer

    if esp32 is None:
        return

    try:

        with esp32_lock:

            if not esp32.is_open:
                return

            waiting = esp32.in_waiting

            if waiting <= 0:
                return

            data = esp32.read(waiting)

        decoded = data.decode(
            errors="ignore"
        )

        mq2_serial_buffer += decoded

        # -------------------------------------------------
        # PROCESS COMPLETE LINES
        # -------------------------------------------------

        while "\n" in mq2_serial_buffer:

            line, mq2_serial_buffer = (
                mq2_serial_buffer.split("\n", 1)
            )

            line = line.strip()

            if not line:
                continue

            # Expected:
            # MQ2:1,VAL:3000
            # MQ2:0,VAL:2600

            if line.startswith("MQ2:"):

                try:

                    parts = line.split(",")

                    if len(parts) >= 2:

                        status_part = parts[0]
                        value_part = parts[1]

                        status = (
                            status_part
                            .split(":", 1)[1]
                        )

                        value = (
                            value_part
                            .split(":", 1)[1]
                        )

                        mq2_fire = (
                            status.strip() == "1"
                        )

                        mq2_raw = int(
                            value.strip()
                        )

                except (
                    IndexError,
                    ValueError
                ):
                    pass

    except Exception as e:

        print(
            "ESP32 READ ERROR:",
            e
        )


# =========================================================
# FIRE DETECTION SETTINGS
# =========================================================

MIN_FIRE_AREA = 60
MIN_FIRE_PIXELS = 80

CONFIRM_TIME = 0.5


# =========================================================
# STATE VARIABLES
# =========================================================

fire_start_time = None

# Camera alarm state
alarm_on = False

# MQ2 alarm state
mq2_alarm_on = False


# =========================================================
# CAMERA INITIALIZATION
# =========================================================

system = platform.system()

if system == "Darwin":

    cap = cv2.VideoCapture(
        0,
        cv2.CAP_AVFOUNDATION
    )

elif system == "Windows":

    cap = cv2.VideoCapture(
        0,
        cv2.CAP_DSHOW
    )

else:

    cap = cv2.VideoCapture(0)


# Camera settings
cap.set(
    cv2.CAP_PROP_FRAME_WIDTH,
    640
)

cap.set(
    cv2.CAP_PROP_FRAME_HEIGHT,
    480
)

cap.set(
    cv2.CAP_PROP_BUFFERSIZE,
    1
)


if not cap.isOpened():

    print(
        "ERROR: Camera could not be opened."
    )

    if esp32 is not None:

        try:
            esp32.close()
        except Exception:
            pass

    raise SystemExit


# =========================================================
# START MESSAGE
# =========================================================

print(
    "======================================"
)

print(
    "🔥 FIRE DETECTION SYSTEM"
)

print(
    "======================================"
)

print(
    "Show a real flame "
    "(lighter/match/candle OK)."
)

print(
    "Press Q to exit."
)


# =========================================================
# FIRE DETECTION FUNCTION
# =========================================================

def detect_fire(frame):

    # -----------------------------------------------------
    # RESIZE
    # -----------------------------------------------------

    small = cv2.resize(
        frame,
        None,
        fx=0.75,
        fy=0.75
    )

    # -----------------------------------------------------
    # BLUR
    # -----------------------------------------------------

    blurred = cv2.GaussianBlur(
        small,
        (5, 5),
        0
    )

    # -----------------------------------------------------
    # HSV
    # -----------------------------------------------------

    hsv = cv2.cvtColor(
        blurred,
        cv2.COLOR_BGR2HSV
    )

    H, S, V = cv2.split(hsv)

    # -----------------------------------------------------
    # BGR
    # -----------------------------------------------------

    B, G, R = cv2.split(
        blurred
    )

    # -----------------------------------------------------
    # FIRE COLOR CONDITIONS
    # -----------------------------------------------------

    fire_condition = (

        (R > 150) &

        (G > 60) &

        (B < 130) &

        (R > G * 1.15) &

        (G > B * 1.05) &

        (S > 90) &

        (V > 140)
    )

    fire_mask = (
        fire_condition.astype(
            np.uint8
        ) * 255
    )

    # -----------------------------------------------------
    # REMOVE NORMAL SKIN
    # -----------------------------------------------------

    skin_condition = (

        (H < 25) &

        (S > 40) &

        (S < 200) &

        (V > 60)
    )

    skin_mask = (
        skin_condition.astype(
            np.uint8
        ) * 255
    )

    # Only remove normal-brightness skin
    bright_pixels = cv2.inRange(
        V,
        220,
        255
    )

    skin_remove = cv2.bitwise_and(
        skin_mask,
        cv2.bitwise_not(
            bright_pixels
        )
    )

    fire_mask = cv2.bitwise_and(
        fire_mask,
        cv2.bitwise_not(
            skin_remove
        )
    )

    # -----------------------------------------------------
    # CLEAN MASK
    # -----------------------------------------------------

    kernel = np.ones(
        (3, 3),
        np.uint8
    )

    fire_mask = cv2.morphologyEx(
        fire_mask,
        cv2.MORPH_OPEN,
        kernel
    )

    fire_mask = cv2.morphologyEx(
        fire_mask,
        cv2.MORPH_CLOSE,
        kernel
    )

    # -----------------------------------------------------
    # FIND CONTOURS
    # -----------------------------------------------------

    contours, _ = cv2.findContours(
        fire_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    boxes = []

    fire_pixels = cv2.countNonZero(
        fire_mask
    )

    # -----------------------------------------------------
    # CHECK FIRE CONTOURS
    # -----------------------------------------------------

    for contour in contours:

        area = cv2.contourArea(
            contour
        )

        if area < MIN_FIRE_AREA:
            continue

        x, y, w, h = cv2.boundingRect(
            contour
        )

        if w < 6 or h < 6:
            continue

        aspect_ratio = w / float(h)

        if aspect_ratio > 5:
            continue

        if aspect_ratio < 0.15:
            continue

        roi = V[
            y:y+h,
            x:x+w
        ]

        if roi.size == 0:
            continue

        brightness = np.mean(
            roi
        )

        if brightness < 120:
            continue

        boxes.append(
            (x, y, w, h, area)
        )

    # -----------------------------------------------------
    # FINAL DECISION
    # -----------------------------------------------------

    fire_detected = (
        fire_pixels >= MIN_FIRE_PIXELS
        and len(boxes) > 0
    )

    return (
        fire_detected,
        fire_pixels,
        boxes
    )


# =========================================================
# MAIN LOOP
# =========================================================

try:

    while True:

        # -------------------------------------------------
        # READ CAMERA FRAME
        # -------------------------------------------------

        ret, frame = cap.read()

        if not ret:

            print(
                "Camera frame error."
            )

            time.sleep(0.05)
            continue

        # Mirror camera
        frame = cv2.flip(
            frame,
            1
        )

        # -------------------------------------------------
        # CAMERA FIRE DETECTION
        # -------------------------------------------------

        (
            fire_detected,
            fire_pixels,
            boxes
        ) = detect_fire(frame)

        # -------------------------------------------------
        # READ MQ2 DATA
        # -------------------------------------------------

        read_esp32_status()

        # -------------------------------------------------
        # FIRE CONFIRMATION TIMER
        # -------------------------------------------------

        if fire_detected:

            if fire_start_time is None:

                fire_start_time = (
                    time.time()
                )

            elapsed = (
                time.time()
                - fire_start_time
            )

        else:

            fire_start_time = None
            elapsed = 0

        # -------------------------------------------------
        # CONFIRM CAMERA FIRE
        # -------------------------------------------------

        confirmed_fire = (
            fire_detected
            and elapsed >= CONFIRM_TIME
        )

        # =================================================
        # CAMERA FIRE DETECTED
        # =================================================

        if confirmed_fire:

            # -------------------------------------------------
            # DRAW STATUS
            # -------------------------------------------------

            cv2.putText(
                frame,
                "!!! FIRE DETECTED (CAMERA) !!!",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                3
            )

            cv2.putText(
                frame,
                "LED1 ON - BUZZER BLINKING",
                (20, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )

            # -------------------------------------------------
            # DRAW FIRE BOXES
            # -------------------------------------------------

            for x, y, w, h, area in boxes:

                # Scale back to original frame
                x = int(
                    x / 0.75
                )

                y = int(
                    y / 0.75
                )

                w = int(
                    w / 0.75
                )

                h = int(
                    h / 0.75
                )

                cv2.rectangle(
                    frame,
                    (x, y),
                    (x + w, y + h),
                    (0, 0, 255),
                    3
                )

            # -------------------------------------------------
            # CAMERA FIRE EVENT
            # -------------------------------------------------

            if not alarm_on:

                print(
                    "🔥 Camera detected fire"
                )

                # ---------------------------------------------
                # SEND ESP32 COMMAND FIRST
                # ---------------------------------------------

                send_to_esp32("1")

                print(
                    "ESP32: LED1 ON / buzzer blinking"
                )

                # ---------------------------------------------
                # TELEGRAM IN BACKGROUND
                # ---------------------------------------------

                if not telegram_camera_sent:

                    print(
                        "📱 Sending camera Telegram alert..."
                    )

                    send_telegram_background(
                        (
                            "🔥 Fire detected by camera!"
                            "\n\n"
                            "Camera has detected a possible "
                            "fire."
                            "\n"
                            "Verifying with gas sensor..."
                        ),
                        frame
                    )

                    telegram_camera_sent = True

                # ---------------------------------------------
                # SAVE ALARM STATE
                # ---------------------------------------------

                alarm_on = True

        # =================================================
        # NO CAMERA FIRE
        # =================================================

        else:

            cv2.putText(
                frame,
                "NO FIRE (CAMERA)",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                3
            )

            cv2.putText(
                frame,
                f"Fire Pixels: {fire_pixels}",
                (20, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2
            )

            # Show confirmation timer
            if fire_detected:

                cv2.putText(
                    frame,
                    f"Checking: {elapsed:.1f}s",
                    (20, 125),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2
                )

            # -------------------------------------------------
            # CLEAR CAMERA ALARM
            # -------------------------------------------------

            if alarm_on:

                print(
                    "✅ Camera fire cleared"
                )

                send_to_esp32("0")

                print(
                    "ESP32: LED1 OFF / buzzer stops blinking"
                )

                alarm_on = False

            telegram_camera_sent = False

        # =================================================
        # MQ2 CONFIRMATION
        # =================================================

        if mq2_fire:

            cv2.putText(
                frame,
                "!!! MQ2 CONFIRMED - REAL FIRE !!!",
                (20, 160),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                3
            )

            cv2.putText(
                frame,
                "LED2 ON - BUZZER STEADY",
                (20, 195),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )

            # -------------------------------------------------
            # SEND MQ2 TELEGRAM ONCE
            # -------------------------------------------------

            if not telegram_mq2_sent:

                print(
                    "🚨 MQ2 SENSOR DETECTED FIRE!"
                )

                print(
                    "📱 Sending Telegram alert..."
                )

                send_telegram_background(
                    (
                        "🚨🚨 FIRE ALERT! 🚨🚨\n\n"
                        "MQ2 gas/smoke sensor has "
                        "detected fire or smoke.\n\n"
                        "Immediate attention required!"
                    ),
                    frame
                )

                telegram_mq2_sent = True

            mq2_alarm_on = True

        else:

            telegram_mq2_sent = False
            mq2_alarm_on = False

            cv2.putText(
                frame,
                "MQ2: clear",
                (20, 160),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (200, 200, 200),
                2
            )

        # -------------------------------------------------
        # SHOW MQ2 RAW VALUE
        # -------------------------------------------------

        if mq2_raw is not None:

            cv2.putText(
                frame,
                f"MQ2 raw: {mq2_raw}",
                (20, 225),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1
            )

        # -------------------------------------------------
        # CAMERA WINDOW
        # -------------------------------------------------

        cv2.imshow(
            "Real Fire Detection",
            frame
        )

        # -------------------------------------------------
        # EXIT
        # -------------------------------------------------

        key = (
            cv2.waitKey(1)
            & 0xFF
        )

        if key == ord("q"):

            break


# =========================================================
# CLEANUP
# =========================================================

except KeyboardInterrupt:

    print(
        "\nProgram interrupted."
    )

finally:

    # -----------------------------------------------------
    # TURN CAMERA ALARM OFF
    # -----------------------------------------------------

    try:

        send_to_esp32("0")

    except Exception:
        pass

    # -----------------------------------------------------
    # CLOSE SERIAL
    # -----------------------------------------------------

    if esp32 is not None:

        try:
            esp32.close()
            print(
                "ESP32 connection closed."
            )
        except Exception:
            pass

    # -----------------------------------------------------
    # CLOSE CAMERA
    # -----------------------------------------------------

    try:
        cap.release()
    except Exception:
        pass

    try:
        cv2.destroyAllWindows()
    except Exception:
        pass

    print(
        "Fire detection stopped."
    )