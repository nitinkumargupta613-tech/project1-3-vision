
// ESP32 FIRE DETECTION SYSTEM

const int MQ2_PIN = 34;
const int LED1_PIN = 25;
const int LED2_PIN = 26;
const int BUZZER_PIN = 27;


// Change this if you need to adjust MQ2 sensitivity
const int MQ2_THRESHOLD = 1800;

// VARIABLES

bool cameraFire = false;
bool mq2Fire = false;

int mq2Value = 0;

// SETUP

void setup() {

  Serial.begin(115200);

  pinMode(LED1_PIN, OUTPUT);
  pinMode(LED2_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  pinMode(MQ2_PIN, INPUT);


  // Everything OFF initially
  digitalWrite(LED1_PIN, LOW);
  digitalWrite(LED2_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);


  Serial.println("================================");
  Serial.println("ESP32 FIRE DETECTION SYSTEM");
  Serial.println("SYSTEM STARTED");
  Serial.println("================================");


  // Give MQ2 some time
  delay(2000);
}

// MAIN LOOP

void loop() {

  // 1. READ COMMAND FROM PYTHON

  while (Serial.available() > 0) {

    char command = Serial.read();


    // Python says CAMERA FIRE
    if (command == '1') {

      cameraFire = true;
    }


    // Python says CAMERA FIRE CLEARED
    else if (command == '0') {

      cameraFire = false;
    }
  }

  // 2. READ MQ2

  mq2Value = analogRead(MQ2_PIN);


  if (mq2Value >= MQ2_THRESHOLD) {

    mq2Fire = true;
  }

  else {

    mq2Fire = false;
  }

  // 3. LED1 = CAMERA FIRE

  if (cameraFire) {

    digitalWrite(LED1_PIN, HIGH);
  }

  else {

    digitalWrite(LED1_PIN, LOW);
  }

  // 4. LED2 = MQ2 FIRE

  if (mq2Fire) {

    digitalWrite(LED2_PIN, HIGH);
  }

  else {

    digitalWrite(LED2_PIN, LOW);
  }

  // 5. BUZZER

  // MQ2 detected smoke/gas
  // -> continuous buzzer

  if (mq2Fire) {

    digitalWrite(BUZZER_PIN, HIGH);
  }


  // Camera detected fire
  // -> blinking buzzer

  else if (cameraFire) {

    digitalWrite(BUZZER_PIN, HIGH);

    delay(150);

    digitalWrite(BUZZER_PIN, LOW);

    delay(150);
  }


  // No fire
  // -> buzzer OFF

  else {

    digitalWrite(BUZZER_PIN, LOW);

    delay(50);
  }

  // 6. SEND MQ2 DATA TO PYTHON

  Serial.print("MQ2:");

  if (mq2Fire) {

    Serial.print("1");
  }

  else {

    Serial.print("0");
  }


  Serial.print(",VAL:");

  Serial.println(mq2Value);


  // Small delay
  delay(100);
}