#include <Servo.h>
#include <SPI.h>
#include <Adafruit_PN532.h>
#include <WiFiS3.h>
#include <ArduinoJson.h>
#include "config.h"
#include "secrets.h"

Servo servos[NUM_SWITCHES];
Adafruit_PN532 pn532(PN532_SS_PIN, &SPI);

bool tagPresent = false;
bool tagDetectorReady = false;
uint8_t activeUid[7] = {0};
uint8_t activeUidLength = 0;
unsigned long lastTagSeenAt = 0;

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

void formatUid(const uint8_t* uid, uint8_t uidLength, char* output, size_t outputSize) {
  size_t offset = 0;
  for (uint8_t i = 0; i < uidLength && offset + 3 < outputSize; ++i) {
    if (i > 0) output[offset++] = ':';
    offset += snprintf(output + offset, outputSize - offset, "%02X", uid[i]);
  }
  output[offset] = '\0';
}

bool uidMatches(const uint8_t* uid, uint8_t uidLength) {
  return uidLength == activeUidLength && memcmp(uid, activeUid, uidLength) == 0;
}

void rememberUid(const uint8_t* uid, uint8_t uidLength) {
  activeUidLength = min(uidLength, static_cast<uint8_t>(sizeof(activeUid)));
  memcpy(activeUid, uid, activeUidLength);
}

void sendTagEvent(const char* event, const uint8_t* uid, uint8_t uidLength) {
  char tagId[3 * sizeof(activeUid)] = {0};
  formatUid(uid, uidLength, tagId, sizeof(tagId));

  JsonDocument doc;
  doc["event"] = event;
  doc["hub"] = HUB_NAME;
  doc["detector"] = DETECTOR_NAME;
  doc["tag_id"] = tagId;
  sendJson(doc);
}

void updateTagDetector() {
  if (!tagDetectorReady) return;

  uint8_t uid[7] = {0};
  uint8_t uidLength = 0;
  const bool detected = pn532.readPassiveTargetID(
      PN532_MIFARE_ISO14443A, uid, &uidLength, TAG_READ_TIMEOUT_MS);
  const unsigned long now = millis();

  if (detected) {
    lastTagSeenAt = now;
    if (!tagPresent || !uidMatches(uid, uidLength)) {
      if (tagPresent) {
        sendTagEvent("tag_removed", activeUid, activeUidLength);
      }
      rememberUid(uid, uidLength);
      tagPresent = true;
      sendTagEvent("tag_detected", activeUid, activeUidLength);
      Serial.print(DETECTOR_NAME);
      Serial.println(" tag detected");
    }
    return;
  }

  if (tagPresent && now - lastTagSeenAt >= TAG_REMOVAL_DELAY_MS) {
    sendTagEvent("tag_removed", activeUid, activeUidLength);
    tagPresent = false;
    activeUidLength = 0;
    Serial.print(DETECTOR_NAME);
    Serial.println(" tag removed");
  }
}

void sendHello() {
  JsonDocument doc;
  doc["event"] = "hello";
  doc["hub"] = HUB_NAME;
  JsonArray sw = doc["switches"].to<JsonArray>();
  for (int i = 0; i < NUM_SWITCHES; i++) sw.add(SWITCHES[i].name);
  JsonArray det = doc["detectors"].to<JsonArray>();
  if (tagDetectorReady) det.add(DETECTOR_NAME);
  JsonArray detectedTags = doc["detected_tags"].to<JsonArray>();
  if (tagDetectorReady && tagPresent) {
    char tagId[3 * sizeof(activeUid)] = {0};
    formatUid(activeUid, activeUidLength, tagId, sizeof(tagId));
    JsonObject tag = detectedTags.add<JsonObject>();
    tag["detector"] = DETECTOR_NAME;
    tag["tag_id"] = tagId;
  }
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
  Serial.println("1 PN532 tag detector");

  SPI.begin();
  pn532.begin();
  if (pn532.getFirmwareVersion() != 0 && pn532.SAMConfig()) {
    tagDetectorReady = true;
    Serial.println("PN532 ready");
  } else {
    Serial.println("PN532 initialization failed; switch control remains available");
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
  updateTagDetector();
  updateLed();
}
