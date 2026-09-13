import cv2
import mediapipe as mp
import numpy as np
import wave
import os
import pygame
import time
import serial

ESP32_PORT = "COMS"
BAUD_RATE = 115200

try:
    esp32 = serial.Serial(
        ESP32_PORT,
        BAUD_RATE,
        timeout=1
    )

    time.sleep(2)
    print("ESP32 connected!")

except serial.SerialException as e:
    print("WARNING: ESP32 not connected.")
    print(e)
    esp32 = None

sample_rate = 44100

frequencies = [
    261.63,   # C
    293.66,   # D
    329.63,   # E
    349.23,   # F
    392.00,   # G
    440.00,   # A
    493.88,   # B
    523.25    # C2
]

note_names = ["C", "D", "E", "F", "G", "A", "B", "C2"]

note_files = []


for i, freq in enumerate(frequencies):

    filename = f"note_{i}.wav"

    duration = 1.0

    t = np.linspace(
        0,
        duration,
        int(sample_rate * duration),
        endpoint=False
    )

    # Piano-like sound using harmonics
    sound = (
        np.sin(2 * np.pi * freq * t)
        + 0.5 * np.sin(2 * np.pi * 2 * freq * t)
        + 0.25 * np.sin(2 * np.pi * 3 * freq * t)
        + 0.1 * np.sin(2 * np.pi * 4 * freq * t)
    )

    # Exponential decay
    envelope = np.exp(-3 * t)

    sound = sound * envelope

    # Convert to 16-bit audio
    sound = sound / np.max(np.abs(sound))
    sound = (sound * 32767).astype(np.int16)

    with wave.open(filename, "w") as wf:

        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(sound.tobytes())

    note_files.append(filename)


# ============================================================
# PYGAME AUDIO
# ============================================================

pygame.mixer.init(
    frequency=44100,
    size=-16,
    channels=1,
    buffer=512
)

pygame.mixer.set_num_channels(8)

sounds = [
    pygame.mixer.Sound(file)
    for file in note_files
]

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)


cap = cv2.VideoCapture(0)


num_keys = 8

last_key = -1

last_play_time = 0

COOLDOWN = 0.4


last_led_command = None


def control_led(key):

    global last_led_command

    if esp32 is None:
        return

    # No key pressed
    if key == -1:

        command = '0'

    # C -> LED1
    elif key == 0:

        command = '1'

    # D -> LED2
    elif key == 1:

        command = '2'

    # E -> LED3
    elif key == 2:

        command = '3'

    # F -> LED4
    elif key == 3:

        command = '4'

    # G -> LED1
    elif key == 4:

        command = '1'

    # A -> LED2
    elif key == 5:

        command = '2'

    # B -> LED3
    elif key == 6:

        command = '3'

    # C2 -> LED4
    elif key == 7:

        command = '4'

    # Send command only when LED state changes
    if command != last_led_command:

        esp32.write(command.encode())

        last_led_command = command


while True:

    success, frame = cap.read()

    if not success:
        break

    # Mirror camera
    frame = cv2.flip(frame, 1)

    height, width, _ = frame.shape

    # Convert BGR -> RGB
    rgb_frame = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    # MediaPipe processing
    result = hands.process(rgb_frame)

    pressed_key = -1


    if result.multi_hand_landmarks:

        for hand_landmarks in result.multi_hand_landmarks:

            mp_draw.draw_landmarks(
                frame,
                hand_landmarks,
                mp_hands.HAND_CONNECTIONS
            )

            # Index fingertip = landmark 8
            fingertip = hand_landmarks.landmark[8]

            x = int(fingertip.x * width)
            y = int(fingertip.y * height)


            # Draw fingertip
            cv2.circle(
                frame,
                (x, y),
                10,
                (0, 255, 0),
                -1
            )
        

            piano_top = int(height * 0.65)

            piano_bottom = height

            key_width = width // num_keys


            if piano_top <= y <= piano_bottom:

                key = x // key_width

                if 0 <= key < num_keys:

                    pressed_key = key


    control_led(pressed_key)


    # ========================================================
    # PLAY SOUND
    # ========================================================

    current_time = time.time()

    if pressed_key != -1:

        if (
            pressed_key != last_key
            or current_time - last_play_time > COOLDOWN
        ):

            sounds[pressed_key].play()

            last_play_time = current_time

            last_key = pressed_key


    else:

        last_key = -1


    # ========================================================
    # DRAW PIANO KEYS
    # ========================================================

    piano_top = int(height * 0.65)

    key_width = width // num_keys


    overlay = frame.copy()


    for i in range(num_keys):

        x1 = i * key_width

        x2 = (i + 1) * key_width


        if i == pressed_key:

            cv2.rectangle(
                overlay,
                (x1, piano_top),
                (x2, height),
                (0, 255, 0),
                -1
            )


        cv2.rectangle(
            frame,
            (x1, piano_top),
            (x2, height),
            (255, 255, 255),
            2
        )


        cv2.putText(
            frame,
            note_names[i],
            (x1 + 20, height - 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2
        )


    # Transparent key highlight
    frame = cv2.addWeighted(
        overlay,
        0.25,
        frame,
        0.75,
        0
    )

    cv2.putText(
        frame,
        "AI Virtual Piano",
        (30, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (255, 255, 255),
        2
    )


    cv2.putText(
        frame,
        "ESP32 + 4 LED Mode",
        (30, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )


    cv2.putText(
        frame,
        "Point index finger at a key",
        (30, 115),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2
    )


    cv2.imshow(
        "AI Virtual Piano",
        frame
    )


    

    key_pressed = cv2.waitKey(1) & 0xFF

    if key_pressed == ord('q') or key_pressed == 27:

        break



cap.release()

cv2.destroyAllWindows()

pygame.mixer.quit()


if esp32:

    try:

        # Turn all LEDs OFF
        esp32.write(b'0')

        time.sleep(0.1)

        esp32.close()

    except:

        pass


# Delete generated WAV files
for file in note_files:

    try:

        os.remove(file)

    except:

        pass
