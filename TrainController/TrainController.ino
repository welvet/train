#include <Servo.h>
#include <WiFiS3.h>
#include <ArduinoJson.h>
#include "config.h"
#include "secrets.h"

Servo servos[NUM_SWITCHES];
bool detectorState[NUM_DETECTORS];

unsigned long servoStartedAt[NUM_SWITCHES] = {0};
bool servoActive[NUM_SWITCHES] = {false};

WiFiClient tcp;
unsigned long lastConnectAttempt = 0;
char lineBuf[256];
int lineLen = 0;

// --- Servo control ---

bool moveSwitch(int id, int angle) {
  servos[id].attach(SWITCHES[id].pin);
  servos[id].write(angle);
  servoActive[id] = true;
  servoStartedAt[id] = millis();
  return true;
}

void updateServos() {
  for (int i = 0; i < NUM_SWITCHES; i++) {
    if (servoActive[i] && millis() - servoStartedAt[i] >= SERVO_SETTLE_MS) {
      servos[i].detach();
      servoActive[i] = false;
    }
  }
}

// --- Detectors ---

bool readDetector(int id) {
  if (DETECTORS[id].activeLow)
    return digitalRead(DETECTORS[id].pin) == LOW;
  else
    return digitalRead(DETECTORS[id].pin) == HIGH;
}

void updateDetectors() {
  for (int i = 0; i < NUM_DETECTORS; i++) {
    bool current = readDetector(i);
    if (current != detectorState[i]) {
      detectorState[i] = current;
      Serial.print(DETECTORS[i].name);
      Serial.println(current ? " TRIGGERED" : " clear");
      sendDetectorEvent(i, current);
    }
  }
}

void updateLed() {
  if (!tcp.connected()) {
    digitalWrite(LED_BUILTIN, (millis() / 150) % 2);
    return;
  }
  digitalWrite(LED_BUILTIN, LOW);
}

// --- TCP send ---

void sendJson(JsonDocument& doc) {
  if (!tcp.connected()) return;
  serializeJson(doc, tcp);
  tcp.println();
}

void sendDetectorEvent(int id, bool triggered) {
  JsonDocument doc;
  doc["event"] = "detector";
  doc["hub"] = HUB_NAME;
  doc["name"] = DETECTORS[id].name;
  doc["triggered"] = triggered;
  sendJson(doc);
}

void sendHello() {
  JsonDocument doc;
  doc["event"] = "hello";
  doc["hub"] = HUB_NAME;
  JsonArray sw = doc["switches"].to<JsonArray>();
  for (int i = 0; i < NUM_SWITCHES; i++) sw.add(SWITCHES[i].name);
  JsonArray det = doc["detectors"].to<JsonArray>();
  for (int i = 0; i < NUM_DETECTORS; i++) det.add(DETECTORS[i].name);
  sendJson(doc);
}

// --- TCP receive ---

int findSwitch(const char* name) {
  for (int i = 0; i < NUM_SWITCHES; i++) {
    if (strcmp(SWITCHES[i].name, name) == 0) return i;
  }
  return -1;
}

void handleCommand(const char* line) {
  JsonDocument doc;
  if (deserializeJson(doc, line)) return;

  const char* cmd = doc["cmd"];
  if (!cmd) return;

  if (strcmp(cmd, "move") == 0) {
    int id = findSwitch(doc["switch"]);
    if (id < 0) return;
    int angle = doc["angle"];
    bool ok = moveSwitch(id, angle);
    Serial.print(SWITCHES[id].name);
    Serial.print(ok ? " moving to " : " busy, rejected ");
    Serial.println(angle);

    JsonDocument resp;
    resp["event"] = "move_ack";
    resp["hub"] = HUB_NAME;
    resp["switch"] = SWITCHES[id].name;
    resp["angle"] = angle;
    resp["ok"] = ok;
    sendJson(resp);
  } else if (strcmp(cmd, "ping") == 0) {
    JsonDocument resp;
    resp["event"] = "pong";
    resp["hub"] = HUB_NAME;
    sendJson(resp);
  }
}

void readTcp() {
  while (tcp.available()) {
    char c = tcp.read();
    if (c == '\n') {
      lineBuf[lineLen] = '\0';
      if (lineLen > 0) handleCommand(lineBuf);
      lineLen = 0;
    } else if (lineLen < (int)sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    }
  }
}

// --- TCP connect ---

void updateConnection() {
  if (tcp.connected()) return;
  if (millis() - lastConnectAttempt < RECONNECT_MS) return;
  lastConnectAttempt = millis();
  Serial.print("Connecting to backend ");
  Serial.print(BACKEND_HOST);
  Serial.print(":");
  Serial.println(BACKEND_PORT);
  if (tcp.connect(BACKEND_HOST, BACKEND_PORT)) {
    Serial.println("Connected to backend");
    sendHello();
  }
}

// --- Setup & Loop ---

void setup() {
  Serial.begin(9600);

  pinMode(LED_BUILTIN, OUTPUT);

  Serial.print("[");
  Serial.print(HUB_NAME);
  Serial.print("] ");
  Serial.print(NUM_SWITCHES);
  Serial.print(" switches, ");
  Serial.print(NUM_DETECTORS);
  Serial.println(" detectors");

  for (int i = 0; i < NUM_DETECTORS; i++) {
    pinMode(DETECTORS[i].pin, INPUT);
    detectorState[i] = false;
  }

  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    delay(250);
    if (++attempts % 4 == 0) Serial.print(".");
    if (attempts > 80) {
      Serial.println("\nRetrying WiFi...");
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      attempts = 0;
    }
  }
  digitalWrite(LED_BUILTIN, LOW);

  Serial.println();
  Serial.print("Connected! IP: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  updateConnection();
  readTcp();
  updateServos();
  updateDetectors();
  updateLed();
}
