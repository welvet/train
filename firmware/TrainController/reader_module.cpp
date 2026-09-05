#include "reader_module.h"

#include <string.h>

namespace train {

bool ReaderModule::setup() {
  SPI.begin();
  for (int index = 0; index < READER_COUNT; ++index) {
    readers_[index] = new Adafruit_PN532(READERS[index].ssPin, &SPI);
    readers_[index]->begin();
    ReaderState& state = model_.readers[index];
    state.ready =
        readers_[index]->getFirmwareVersion() != 0 && readers_[index]->SAMConfig();
    Serial.print(READERS[index].id);
    Serial.println(state.ready ? " ready" : " unavailable");
  }
  return true;
}

void ReaderModule::trigger() {
  if (READER_COUNT == 0) return;
  updateReader(nextReaderIndex_);
  if (++nextReaderIndex_ >= READER_COUNT) nextReaderIndex_ = 0;
}

void ReaderModule::updateReader(int index) {
  ReaderState& state = model_.readers[index];
  if (!state.ready) return;

  uint8_t uid[7] = {0};
  uint8_t uidLength = 0;
  const ReaderConfig& config = READERS[index];
  const bool detected = readers_[index]->readPassiveTargetID(
      PN532_MIFARE_ISO14443A, uid, &uidLength, config.readTimeoutMs);
  const unsigned long now = millis();

  if (detected) {
    state.lastSeenAt = now;
    if (!state.tagPresent || !uidMatches(state, uid, uidLength)) {
      rememberUid(state, uid, uidLength);
      state.tagPresent = true;
      publishChange(index, true);
      Serial.print(config.id);
      Serial.println(" tag detected");
    }
    return;
  }

  if (state.tagPresent && now - state.lastSeenAt >= config.removalDelayMs) {
    const TagChangedEvent removed(index, false, state.uid, state.uidLength);
    state.tagPresent = false;
    state.uidLength = 0;
    bus_.publish(removed);
    Serial.print(config.id);
    Serial.println(" tag removed");
  }
}

void ReaderModule::publishChange(int index, bool detected) {
  const ReaderState& state = model_.readers[index];
  bus_.publish(TagChangedEvent(index, detected, state.uid, state.uidLength));
}

bool ReaderModule::uidMatches(
    const ReaderState& state,
    const uint8_t* uid,
    uint8_t length) {
  return length == state.uidLength && memcmp(uid, state.uid, length) == 0;
}

void ReaderModule::rememberUid(
    ReaderState& state,
    const uint8_t* uid,
    uint8_t length) {
  state.uidLength = min(length, static_cast<uint8_t>(sizeof(state.uid)));
  memcpy(state.uid, uid, state.uidLength);
}

}  // namespace train
