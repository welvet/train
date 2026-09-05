#ifndef TRAIN_CONTROLLER_EVENTS_H
#define TRAIN_CONTROLLER_EVENTS_H

#include <Arduino.h>
#include <ArduinoJson.h>

#include <string.h>

namespace train {

enum class EventType : uint8_t {
  WifiConnected,
  WifiDisconnected,
  BackendConnected,
  BackendDisconnected,
  InboundLine,
  OutboundDocument,
  MoveSwitchRequested,
  SwitchMoved,
  TagChanged,
};

class Event {
 public:
  EventType type() const { return type_; }

 protected:
  explicit Event(EventType type) : type_(type) {}

 private:
  EventType type_;
};

struct WifiConnectedEvent final : Event {
  WifiConnectedEvent() : Event(EventType::WifiConnected) {}
};

struct WifiDisconnectedEvent final : Event {
  WifiDisconnectedEvent() : Event(EventType::WifiDisconnected) {}
};

struct BackendConnectedEvent final : Event {
  BackendConnectedEvent() : Event(EventType::BackendConnected) {}
};

struct BackendDisconnectedEvent final : Event {
  BackendDisconnectedEvent() : Event(EventType::BackendDisconnected) {}
};

struct InboundLineEvent final : Event {
  explicit InboundLineEvent(const char* value)
      : Event(EventType::InboundLine), value(value) {}

  const char* value;
};

struct OutboundDocumentEvent final : Event {
  explicit OutboundDocumentEvent(JsonDocument& document)
      : Event(EventType::OutboundDocument), document(document) {}

  JsonDocument& document;
};

struct MoveSwitchRequestedEvent final : Event {
  MoveSwitchRequestedEvent(
      const char* switchId,
      bool hasAngle,
      int angle,
      const char* position)
      : Event(EventType::MoveSwitchRequested),
        switchId(switchId),
        hasAngle(hasAngle),
        angle(angle),
        position(position) {}

  const char* switchId;
  bool hasAngle;
  int angle;
  const char* position;
};

struct SwitchMovedEvent final : Event {
  SwitchMovedEvent(int switchIndex, int angle, bool ok)
      : Event(EventType::SwitchMoved),
        switchIndex(switchIndex),
        angle(angle),
        ok(ok) {}

  int switchIndex;
  int angle;
  bool ok;
};

struct TagChangedEvent final : Event {
  TagChangedEvent(
      int readerIndex,
      bool detected,
      const uint8_t* uid,
      uint8_t uidLength)
      : Event(EventType::TagChanged),
        readerIndex(readerIndex),
        detected(detected),
        uidLength(min(uidLength, static_cast<uint8_t>(sizeof(this->uid)))) {
    memcpy(this->uid, uid, this->uidLength);
  }

  int readerIndex;
  bool detected;
  uint8_t uid[7] = {0};
  uint8_t uidLength;
};

}  // namespace train

#endif
