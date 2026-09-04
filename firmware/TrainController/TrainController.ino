#include <Adafruit_PN532.h>
#include <ArduinoJson.h>
#include <Servo.h>
#include <SPI.h>
#include <WiFiS3.h>

#include "generated_config.h"

struct ReaderState {
  bool ready = false;
  bool tagPresent = false;
  uint8_t uid[7] = {0};
  uint8_t uidLength = 0;
  unsigned long lastSeenAt = 0;
};

Servo servos[SWITCH_STORAGE_SIZE];
bool servoActive[SWITCH_STORAGE_SIZE] = {false};
unsigned long servoStartedAt[SWITCH_STORAGE_SIZE] = {0};
Adafruit_PN532* readers[READER_STORAGE_SIZE] = {nullptr};
ReaderState readerStates[READER_STORAGE_SIZE];

WiFiClient tcp;
unsigned long lastConnectAttempt = 0;
char lineBuffer[256];
int lineLength = 0;
int nextReaderIndex = 0;

void sendJson(JsonDocument& document) {
  if (!tcp.connected()) return;
  serializeJson(document, tcp);
  tcp.println();
}

void formatUid(const uint8_t* uid, uint8_t length, char* output, size_t size) {
  size_t offset = 0;
  for (uint8_t index = 0; index < length && offset + 3 < size; ++index) {
    if (index > 0) output[offset++] = ':';
    offset += snprintf(output + offset, size - offset, "%02X", uid[index]);
  }
  output[offset] = '\0';
}

bool uidMatches(const ReaderState& state, const uint8_t* uid, uint8_t length) {
  return length == state.uidLength && memcmp(uid, state.uid, length) == 0;
}

void rememberUid(ReaderState& state, const uint8_t* uid, uint8_t length) {
  state.uidLength = min(length, static_cast<uint8_t>(sizeof(state.uid)));
  memcpy(state.uid, uid, state.uidLength);
}

void sendTagEvent(const char* event, int readerIndex) {
  const ReaderConfig& config = READERS[readerIndex];
  const ReaderState& state = readerStates[readerIndex];
  char tagId[3 * sizeof(state.uid)] = {0};
  formatUid(state.uid, state.uidLength, tagId, sizeof(tagId));

  JsonDocument document;
  document["event"] = event;
  document["hub"] = HUB_ID;
  document["detector"] = config.id;
  document["tag_id"] = tagId;
  sendJson(document);
}

void updateReader(int index) {
  ReaderState& state = readerStates[index];
  if (!state.ready) return;

  uint8_t uid[7] = {0};
  uint8_t uidLength = 0;
  const ReaderConfig& config = READERS[index];
  const bool detected = readers[index]->readPassiveTargetID(
      PN532_MIFARE_ISO14443A, uid, &uidLength, config.readTimeoutMs);
  const unsigned long now = millis();

  if (detected) {
    state.lastSeenAt = now;
    if (!state.tagPresent || !uidMatches(state, uid, uidLength)) {
      if (state.tagPresent) sendTagEvent("tag_removed", index);
      rememberUid(state, uid, uidLength);
      state.tagPresent = true;
      sendTagEvent("tag_detected", index);
      Serial.print(config.id);
      Serial.println(" tag detected");
    }
    return;
  }

  if (state.tagPresent && now - state.lastSeenAt >= config.removalDelayMs) {
    sendTagEvent("tag_removed", index);
    state.tagPresent = false;
    state.uidLength = 0;
    Serial.print(config.id);
    Serial.println(" tag removed");
  }
}

bool moveSwitch(int index, int angle) {
  servos[index].attach(SWITCHES[index].pin);
  servos[index].write(angle);
  servoActive[index] = true;
  servoStartedAt[index] = millis();
  return true;
}

void updateServos() {
  for (int index = 0; index < SWITCH_COUNT; ++index) {
    if (servoActive[index] && millis() - servoStartedAt[index] >= SERVO_SETTLE_MS) {
      servos[index].detach();
      servoActive[index] = false;
    }
  }
}

int findSwitch(const char* id) {
  for (int index = 0; index < SWITCH_COUNT; ++index) {
    if (strcmp(SWITCHES[index].id, id) == 0) return index;
  }
  return -1;
}

bool resolveSwitchAngle(int index, JsonDocument& document, int& angle) {
  if (document["angle"].is<int>()) {
    angle = document["angle"];
    return angle >= 0 && angle <= 180;
  }
  const char* position = document["position"];
  if (!position) return false;
  if (strcmp(position, "straight") == 0) {
    angle = SWITCHES[index].straightAngle;
    return true;
  }
  if (strcmp(position, "diverge") == 0) {
    angle = SWITCHES[index].divergeAngle;
    return true;
  }
  return false;
}

void sendHello() {
  JsonDocument document;
  document["event"] = "hello";
  document["hub"] = HUB_ID;
  JsonArray switches = document["switches"].to<JsonArray>();
  for (int index = 0; index < SWITCH_COUNT; ++index) switches.add(SWITCHES[index].id);
  JsonArray detectors = document["detectors"].to<JsonArray>();
  JsonArray detectedTags = document["detected_tags"].to<JsonArray>();
  for (int index = 0; index < READER_COUNT; ++index) {
    const ReaderState& state = readerStates[index];
    if (!state.ready) continue;
    detectors.add(READERS[index].id);
    if (state.tagPresent) {
      char tagId[3 * sizeof(state.uid)] = {0};
      formatUid(state.uid, state.uidLength, tagId, sizeof(tagId));
      JsonObject tag = detectedTags.add<JsonObject>();
      tag["detector"] = READERS[index].id;
      tag["tag_id"] = tagId;
    }
  }
  sendJson(document);
}

void handleCommand(const char* line) {
  JsonDocument document;
  if (deserializeJson(document, line)) return;
  const char* command = document["cmd"];
  if (!command) return;

  if (strcmp(command, "move") == 0) {
    int index = findSwitch(document["switch"]);
    if (index < 0) return;
    int angle = 0;
    bool ok = resolveSwitchAngle(index, document, angle);
    if (ok) moveSwitch(index, angle);
    JsonDocument response;
    response["event"] = "move_ack";
    response["hub"] = HUB_ID;
    response["switch"] = SWITCHES[index].id;
    response["angle"] = angle;
    response["ok"] = ok;
    sendJson(response);
  } else if (strcmp(command, "ping") == 0) {
    JsonDocument response;
    response["event"] = "pong";
    response["hub"] = HUB_ID;
    sendJson(response);
  }
}

void readTcp() {
  while (tcp.available()) {
    char value = tcp.read();
    if (value == '\n') {
      lineBuffer[lineLength] = '\0';
      if (lineLength > 0) handleCommand(lineBuffer);
      lineLength = 0;
    } else if (lineLength < static_cast<int>(sizeof(lineBuffer)) - 1) {
      lineBuffer[lineLength++] = value;
    }
  }
}

void updateConnection() {
  if (tcp.connected()) return;
  if (millis() - lastConnectAttempt < RECONNECT_MS) return;
  lastConnectAttempt = millis();
  if (tcp.connect(BACKEND_HOST, BACKEND_PORT)) sendHello();
}

void updateLed() {
  digitalWrite(LED_BUILTIN, tcp.connected() ? LOW : (millis() / 150) % 2);
}

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  pinMode(LED_BUILTIN, OUTPUT);
  SPI.begin();
  for (int index = 0; index < READER_COUNT; ++index) {
    readers[index] = new Adafruit_PN532(READERS[index].ssPin, &SPI);
    readers[index]->begin();
    ReaderState& state = readerStates[index];
    state.ready = readers[index]->getFirmwareVersion() != 0 && readers[index]->SAMConfig();
    Serial.print(READERS[index].id);
    Serial.println(state.ready ? " ready" : " unavailable");
  }

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    delay(250);
    if (++attempts > 80) {
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      attempts = 0;
    }
  }
}

void loop() {
  updateConnection();
  readTcp();
  updateServos();
  if (READER_COUNT > 0) {
    updateReader(nextReaderIndex);
    ++nextReaderIndex;
    if (nextReaderIndex >= READER_COUNT) nextReaderIndex = 0;
  }
  updateLed();
}
