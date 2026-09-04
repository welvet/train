#include <SPI.h>
#include <Adafruit_PN532.h>

#include "firmware_config.h"

Adafruit_PN532 pn532(PN532_SS_PIN, &SPI);

bool tagPresent = false;
uint8_t activeUid[7] = {0};
uint8_t activeUidLength = 0;
unsigned long lastTagSeenAt = 0;
unsigned long lastPollHeartbeatAt = 0;
unsigned long successfulReads = 0;

void logPrefix(const char* level, const char* stage) {
  Serial.print('[');
  Serial.print(millis());
  Serial.print(" ms] [");
  Serial.print(level);
  Serial.print("] [");
  Serial.print(stage);
  Serial.print("] ");
}

void printUid(const uint8_t* uid, uint8_t uidLength) {
  for (uint8_t i = 0; i < uidLength; ++i) {
    if (uid[i] < 0x10) {
      Serial.print('0');
    }
    Serial.print(uid[i], HEX);
    if (i + 1 < uidLength) {
      Serial.print(':');
    }
  }
}

bool uidMatches(const uint8_t* uid, uint8_t uidLength) {
  if (uidLength != activeUidLength) {
    return false;
  }

  for (uint8_t i = 0; i < uidLength; ++i) {
    if (uid[i] != activeUid[i]) {
      return false;
    }
  }
  return true;
}

void rememberUid(const uint8_t* uid, uint8_t uidLength) {
  activeUidLength = min(uidLength, static_cast<uint8_t>(sizeof(activeUid)));
  for (uint8_t i = 0; i < activeUidLength; ++i) {
    activeUid[i] = uid[i];
  }
}

void stopWithError(const char* message) {
  logPrefix("ERROR", "INIT");
  Serial.println(message);
  logPrefix("ERROR", "INIT");
  Serial.println("Check power, SPI mode, wiring, and SS=D4; then reset the board.");

  while (true) {
    delay(1000);
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  unsigned long serialWaitStartedAt = millis();
  while (!Serial && millis() - serialWaitStartedAt < 3000) {
    delay(10);
  }

  Serial.println();
  Serial.println("============================================================");
  logPrefix("INFO", "BOOT");
  Serial.print(FIRMWARE_NAME);
  Serial.print(" v");
  Serial.println(FIRMWARE_VERSION);
  logPrefix("INFO", "BOOT");
  Serial.println("Arduino-only diagnostic mode; Wi-Fi and motors are disabled.");

  logPrefix("INFO", "WIRING");
  Serial.println("PN532: VCC=5V GND=GND SCK=D13 MOSI=D11 MISO=D12 SS=D4");
  logPrefix("INFO", "SPI");
  Serial.println("Starting hardware SPI and PN532 interface...");
  SPI.begin();
  pn532.begin();

  logPrefix("INFO", "PROBE");
  Serial.println("Reading PN532 firmware version...");
  const uint32_t versionData = pn532.getFirmwareVersion();
  if (versionData == 0) {
    stopWithError("PN532 did not respond.");
  }

  logPrefix("OK", "PROBE");
  Serial.print("Found chip PN5");
  Serial.println((versionData >> 24) & 0xFF, HEX);
  logPrefix("OK", "PROBE");
  Serial.print("Firmware ");
  Serial.print((versionData >> 16) & 0xFF, DEC);
  Serial.print('.');
  Serial.println((versionData >> 8) & 0xFF, DEC);

  logPrefix("INFO", "CONFIG");
  Serial.println("Configuring the PN532 secure access module (SAM)...");
  if (!pn532.SAMConfig()) {
    stopWithError("SAM configuration failed.");
  }

  logPrefix("OK", "READY");
  Serial.println("Reader configured for ISO14443A tags.");
  logPrefix("INFO", "POLL");
  Serial.println("Waiting for a train tag. Hold the tag close to the antenna...");
}

void loop() {
  uint8_t uid[7] = {0};
  uint8_t uidLength = 0;
  const bool detected = pn532.readPassiveTargetID(
      PN532_MIFARE_ISO14443A, uid, &uidLength, READ_TIMEOUT_MS);
  const unsigned long now = millis();

  if (detected) {
    lastTagSeenAt = now;
    ++successfulReads;

    if (!tagPresent || !uidMatches(uid, uidLength)) {
      const bool replacedTag = tagPresent;
      rememberUid(uid, uidLength);
      tagPresent = true;

      logPrefix("DETECTED", "TAG");
      Serial.print(replacedTag ? "Different tag detected; UID=" : "Train tag detected; UID=");
      printUid(uid, uidLength);
      Serial.print(" (");
      Serial.print(uidLength);
      Serial.println(" bytes)");
    }
    return;
  }

  if (tagPresent && now - lastTagSeenAt >= TAG_REMOVAL_DELAY_MS) {
    logPrefix("INFO", "TAG");
    Serial.print("Tag removed; last UID=");
    printUid(activeUid, activeUidLength);
    Serial.print(", successful reads=");
    Serial.println(successfulReads);
    tagPresent = false;
    activeUidLength = 0;

    logPrefix("INFO", "POLL");
    Serial.println("Reader re-armed and waiting for the next train tag...");
  }

  if (!tagPresent && now - lastPollHeartbeatAt >= POLL_HEARTBEAT_INTERVAL_MS) {
    lastPollHeartbeatAt = now;
    logPrefix("DEBUG", "POLL");
    Serial.println("Reader alive; no tag detected yet.");
  }
}
