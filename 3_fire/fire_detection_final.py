import cv2
import numpy as np
import serial
import time
import platform
import requests
import threading
# ESP32 SETTINGS
ESP32_PORT = "COM4"
BAUD_RATE = 115200

esp32 = None

try:
    esp32 = serial.Serial(
        ESP32_PORT,
        BAUD_RATE,
        timeout=1
    )
    time.sleep(2)
    print("ESP32 connected!")

except:
    print("ESP32 not connected - Camera only mode.")

# TELEGRAM SETTINGS

TELEGRAM_BOT_TOKEN = "8923452690:AAFsNiM0a1M3IoBkmZZVpkALzKkwDq5DzFU"
TELEGRAM_CHAT_ID = "1897125381"

telegram_camera_sent = False
telegram_mq2_sent = False


def send_telegram_alert(message, frame=None):
    """
    Sends a Telegram message and, when available, a snapshot.
    """

    try:
        if frame is not None:
            success, buffer = cv2.imencode(".jpg", frame)

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
                    timeout=15
                )

                print("Telegram response:", response.text)
                return

        # Text-only fallback
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
            timeout=15
        )

        print("Telegram response:", response.text)

    except Exception as e:
        print("TELEGRAM ERROR:", e)

# MQ2 STATUS (reported back from ESP32)

# These get updated whenever the ESP32 sends a line like:
#   "MQ2:1,VAL:2043"
mq2_fire = False
mq2_raw = None
mq2_serial_buffer = ""


def read_esp32_status():
    """
    Non-blocking read of any lines the ESP32 has sent back
    (MQ2 sensor status). Updates the mq2_fire / mq2_raw globals.
    """
    global mq2_fire, mq2_raw, mq2_serial_buffer

    if not esp32:
        return

    try:
        if esp32.in_waiting > 0:
            data = esp32.read(esp32.in_waiting).decode(errors="ignore")
            mq2_serial_buffer += data

            # Process any complete lines
            while "\n" in mq2_serial_buffer:
                line, mq2_serial_buffer = mq2_serial_buffer.split("\n", 1)
                line = line.strip()

                if line.startswith("MQ2:"):
                    # Format: MQ2:<0|1>,VAL:<raw>
                    try:
                        parts = line.split(",")
                        mq2_fire = (parts[0].split(":")[1] == "1")
                        mq2_raw = int(parts[1].split(":")[1])
                    except (IndexError, ValueError):
                        pass
    except Exception:
        pass

# FIRE SETTINGS

# Tuned to also catch small flames (lighters, matches, candles).
# Lighter flames are small in frame area, flicker quickly, and
# are often less saturated / less bright than a large fire, so
# the thresholds below are relaxed compared to the "big fire only"
# version.

# Lowered so a small lighter flame's blob still counts
MIN_FIRE_AREA = 60
MIN_FIRE_PIXELS = 80

# Fire must be detected continuously for this long before alarming.
# Lowered from 1.0s because small flames flicker fast and may not
# stay "on" for a full second at a time.
CONFIRM_TIME = 0.5

fire_start_time = None
alarm_on = False
mq2_alarm_on = False  # tracks MQ2 state so we only alert on the transition

# CAMERA

system = platform.system()

if system == "Darwin":
    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)

elif system == "Windows":
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

else:
    cap = cv2.VideoCapture(0)


if not cap.isOpened():
    print("ERROR: Camera could not be opened.")
    exit()


print("======================================")
print("🔥 FIRE DETECTION SYSTEM (sensitive mode)")
print("======================================")
print("Show a real flame (lighter/match/candle OK).")
print("Press Q to exit.")

# FIRE DETECTION


def detect_fire(frame):

    small = cv2.resize(
        frame,
        None,
        fx=0.75,
        fy=0.75
    )

    blurred = cv2.GaussianBlur(
        small,
        (5, 5),
        0
    )

    hsv = cv2.cvtColor(
        blurred,
        cv2.COLOR_BGR2HSV
    )

    H, S, V = cv2.split(hsv)

    B, G, R = cv2.split(blurred)

    # FIRE COLOR CONDITIONS (relaxed for small/lighter flames)

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
        fire_condition.astype(np.uint8)
        * 255
    )

    # REMOVE SKIN

    skin_condition = (

        (H < 25) &
        (S > 40) &
        (S < 200) &
        (V > 60)

    )

    skin_mask = (
        skin_condition.astype(np.uint8)
        * 255
    )

    # Only remove normal-brightness skin
    bright_pixels = cv2.inRange(
        V,
        220,
        255
    )

    skin_remove = cv2.bitwise_and(
        skin_mask,
        cv2.bitwise_not(bright_pixels)
    )

    fire_mask = cv2.bitwise_and(
        fire_mask,
        cv2.bitwise_not(skin_remove)
    )

    # CLEAN MASK

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

    # FIND CONTOURS

    contours, _ = cv2.findContours(
        fire_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    boxes = []

    fire_pixels = cv2.countNonZero(
        fire_mask
    )


    for contour in contours:

        area = cv2.contourArea(contour)

        if area < MIN_FIRE_AREA:
            continue

        x, y, w, h = cv2.boundingRect(
            contour
        )

        # Lowered min box size so small lighter flames aren't
        # thrown out just for being small in frame.
        if w < 6 or h < 6:
            continue

        # Avoid extremely thin objects
        aspect_ratio = w / float(h)

        if aspect_ratio > 5:
            continue

        if aspect_ratio < 0.15:
            continue

        # Brightness check (relaxed)
        roi = V[
            y:y+h,
            x:x+w
        ]

        if roi.size == 0:
            continue

        brightness = np.mean(roi)

        if brightness < 120:
            continue

        boxes.append(
            (x, y, w, h, area)
        )

    # FINAL DECISION

    fire_detected = (
        fire_pixels >= MIN_FIRE_PIXELS
        and len(boxes) > 0
    )

    return (
        fire_detected,
        fire_pixels,
        boxes
    )

# MAIN LOOP

while True:

    ret, frame = cap.read()

    if not ret:
        print("Camera frame error.")
        break

    frame = cv2.flip(
        frame,
        1
    )

    # Detect
    fire_detected, fire_pixels, boxes = detect_fire(
        frame
    )

    # Check for MQ2 status updates from ESP32 (non-blocking)
    read_esp32_status()

    # TIMER

    if fire_detected:

        if fire_start_time is None:
            fire_start_time = time.time()

        elapsed = (
            time.time()
            - fire_start_time
        )

    else:

        fire_start_time = None
        elapsed = 0

    # CONFIRMED FIRE (camera stage)

    confirmed_fire = (
        fire_detected
        and elapsed >= CONFIRM_TIME
    )

    # CAMERA FIRE STAGE

    if confirmed_fire:

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

        for x, y, w, h, area in boxes:

            # Scale boxes back to original frame
            x = int(x / 0.75)
            y = int(y / 0.75)
            w = int(w / 0.75)
            h = int(h / 0.75)

            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 0, 255),
                3
            )


        # ESP32 ON (camera stage)
        if not alarm_on:

            print("🔥 Camera detected fire")
            print("ESP32: LED1 ON / buzzer blinking")

            if esp32:
                esp32.write(b'1')

            if not telegram_camera_sent:
                send_telegram_alert(
                    "🔥 Fire detected by camera! Verifying with gas sensor...",
                    frame=frame
                )
                telegram_camera_sent = True

            alarm_on = True

    # NO FIRE (camera stage)

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


        # ESP32 OFF (camera stage)
        if alarm_on:

            print("✅ Camera fire cleared")
            print("ESP32: LED1 OFF / buzzer stops blinking")

            if esp32:
                esp32.write(b'0')

            alarm_on = False

        telegram_camera_sent = False

    # MQ2 STAGE (real fire confirmation, shown on frame)

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

        # Send Telegram alert once when MQ2 changes to FIRE.
        if not telegram_mq2_sent:
            print("🚨 MQ2 SENSOR DETECTED FIRE!")
            print("Sending Telegram alert...")

            send_telegram_alert(
                "🚨🚨 FIRE ALERT! 🚨🚨\n\n"
                "MQ2 gas/smoke sensor has detected fire or smoke.\n"
                "Immediate attention required!",
                frame=frame
            )

            telegram_mq2_sent = True

        mq2_alarm_on = True

    else:
        # Reset only after MQ2 becomes clear, allowing a new fire event.
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

    # CAMERA WINDOW

    cv2.imshow(
        "Real Fire Detection",
        frame
    )

    # EXIT

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# CLEANUP

if esp32:

    try:
        esp32.write(b'0')
        time.sleep(0.2)
        esp32.close()
    except:
        pass

cap.release()
cv2.destroyAllWindows()

print("Fire detection stopped.")