#include "reader_module.h"

#include <string.h>

namespace train {

bool ReaderModule::setup() {
  return bus_.subscribe(
      eventMask(EventType::ConfigurationChanged), this, receive);
}

void ReaderModule::trigger() {
  if (model_.configurationPending) {
    provisionNextReader();
    return;
  }
  if (!model_.configurationApplied || model_.config.readerCount == 0) return;
  for (int index = 0; index < model_.config.readerCount; ++index) {
    updateReader(index);
  }
}

void ReaderModule::receive(void* context, const Event&) {
  static_cast<ReaderModule*>(context)->beginConfiguration();
}

void ReaderModule::beginConfiguration() {
  for (int index = 0; index < MAX_READERS; ++index) {
    readers_[index] = nullptr;
    model_.readers[index] = {};
  }
  provisioningIndex_ = 0;
  if (model_.config.readerCount == 0) {
    model_.configurationPending = false;
    model_.configurationApplied = true;
    bus_.publish(HardwareConfiguredEvent());
    return;
  }
  SPI.begin();
  for (int index = 0; index < model_.config.readerCount; ++index) {
    pinMode(model_.config.readers[index].ssPin, OUTPUT);
    digitalWrite(model_.config.readers[index].ssPin, HIGH);
  }
}

void ReaderModule::provisionNextReader() {
  if (provisioningIndex_ >= model_.config.readerCount) {
    model_.configurationPending = false;
    model_.configurationApplied = true;
    bus_.publish(HardwareConfiguredEvent());
    return;
  }
  const int index = provisioningIndex_++;
  const ReaderConfig& config = model_.config.readers[index];
  const int cacheIndex = config.ssPin - MIN_COMPONENT_PIN;
  if (pinCache_[cacheIndex] == nullptr) {
    pinCache_[cacheIndex] = new Adafruit_PN532(config.ssPin, &SPI);
  }
  readers_[index] = pinCache_[cacheIndex];
  readers_[index]->begin();
  ReaderState& state = model_.readers[index];
  state.ready =
      readers_[index]->getFirmwareVersion() != 0 && readers_[index]->SAMConfig();
  if (state.ready) scanReader(index, false);
}

void ReaderModule::updateReader(int index) {
  scanReader(index, true);
}

void ReaderModule::scanReader(int index, bool publish) {
  ReaderState& state = model_.readers[index];
  if (!state.ready) return;

  uint8_t uid[7] = {0};
  uint8_t uidLength = 0;
  const ReaderConfig& config = model_.config.readers[index];
  const bool detected = readers_[index]->readPassiveTargetID(
      PN532_MIFARE_ISO14443A, uid, &uidLength, config.readTimeoutMs);
  const unsigned long now = millis();

  if (detected) {
    state.lastSeenAt = now;
    if (!state.tagPresent || !uidMatches(state, uid, uidLength)) {
      rememberUid(state, uid, uidLength);
      state.tagPresent = true;
      if (publish) publishChange(index, true);
    }
    return;
  }

  if (state.tagPresent && now - state.lastSeenAt >= config.removalDelayMs) {
    const TagChangedEvent removed(index, false, state.uid, state.uidLength);
    state.tagPresent = false;
    state.uidLength = 0;
    if (publish) bus_.publish(removed);
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
