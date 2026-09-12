#include <ESP32Servo.h>

Servo myServo;

// PIN DEFINITIONS

#define SERVO_PIN 13
#define BUZZER_PIN 25
#define LED_PIN 26

// VARIABLES

bool drowsy = false;

// SETUP

void setup() {

  Serial.begin(115200);

  // Attach servo
  myServo.attach(SERVO_PIN);

  // Output pins
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);

  // Initial state
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_PIN, LOW);

  // Servo starts at 0 degrees
  myServo.write(0);

  Serial.println("================================");
  Serial.println("DRIVER DROWSINESS SYSTEM");
  Serial.println("ESP32 READY");
  Serial.println("SERVO STARTED");
  Serial.println("================================");
}

// LOOP

void loop() {

  // CHECK COMMAND FROM PYTHON

  if (Serial.available()) {

    char command = Serial.read();

    // D = DROWSINESS DETECTED

    if (command == 'D') {

      drowsy = true;

      // Stop servo
      myServo.write(0);

      // LED ON
      digitalWrite(LED_PIN, HIGH);

      Serial.println("DROWSINESS DETECTED");
      Serial.println("SERVO STOPPED");
      Serial.println("LED ON");
    }

    // A = AWAKE

    if (command == 'A') {

      drowsy = false;

      // LED OFF
      digitalWrite(LED_PIN, LOW);

      // Buzzer OFF
      noTone(BUZZER_PIN);

      Serial.println("AWAKE");
      Serial.println("SERVO STARTING");
    }
  }

  // SERVO MOVEMENT

  if (!drowsy) {

    // Move servo 0 → 180

    for (int angle = 0; angle <= 180 && !drowsy; angle += 4) {

      // Check Python command
      if (Serial.available()) {

        char command = Serial.read();

        if (command == 'D') {

          drowsy = true;

          myServo.write(0);

          digitalWrite(LED_PIN, HIGH);

          break;
        }
      }

      myServo.write(angle);

      delay(5);
    }

    // Move servo 180 → 0

    for (int angle = 180; angle >= 0 && !drowsy; angle -= 4) {

      // Check Python command
      if (Serial.available()) {

        char command = Serial.read();

        if (command == 'D') {

          drowsy = true;

          myServo.write(0);

          digitalWrite(LED_PIN, HIGH);

          break;
        }
      }

      myServo.write(angle);

      delay(5);
    }
  }

  // DROWSINESS ALARM

  if (drowsy) {

    // Buzzer ON
    tone(BUZZER_PIN, 2000);

    delay(300);

    // Buzzer OFF
    noTone(BUZZER_PIN);

    delay(300);
  }
}