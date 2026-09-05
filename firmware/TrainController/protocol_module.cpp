#include "protocol_module.h"

#include <string.h>

namespace train {

bool ProtocolModule::setup() {
  return bus_.subscribe(
      eventMask(EventType::BackendConnected) |
          eventMask(EventType::InboundLine) |
          eventMask(EventType::SwitchMoved) |
          eventMask(EventType::TagChanged),
      this,
      receive);
}

void ProtocolModule::receive(void* context, const Event& event) {
  static_cast<ProtocolModule*>(context)->onEvent(event);
}

void ProtocolModule::onEvent(const Event& event) {
  switch (event.type()) {
    case EventType::BackendConnected:
      sendHello();
      break;
    case EventType::InboundLine:
      handleLine(static_cast<const InboundLineEvent&>(event).value);
      break;
    case EventType::SwitchMoved:
      sendSwitchAcknowledgement(
          static_cast<const SwitchMovedEvent&>(event));
      break;
    case EventType::TagChanged:
      sendTagChange(static_cast<const TagChangedEvent&>(event));
      break;
    default:
      break;
  }
}

void ProtocolModule::handleLine(const char* line) {
  JsonDocument document;
  if (deserializeJson(document, line)) return;
  const char* command = document["cmd"];
  if (command == nullptr) return;

  if (strcmp(command, "move") == 0) {
    const char* switchId = document["switch"];
    if (switchId == nullptr) return;
    const MoveSwitchRequestedEvent request{
        switchId,
        document["angle"].is<int>(),
        document["angle"] | 0,
        document["position"],
        document["request_id"],
    };
    bus_.publish(request);
  } else if (strcmp(command, "ping") == 0) {
    sendPong();
  }
}

void ProtocolModule::sendHello() {
  JsonDocument document;
  document["event"] = "hello";
  document["hub"] = HUB_ID;
  JsonArray switches = document["switches"].to<JsonArray>();
  for (int index = 0; index < SWITCH_COUNT; ++index) {
    switches.add(SWITCHES[index].id);
  }

  JsonArray detectors = document["detectors"].to<JsonArray>();
  JsonArray detectedTags = document["detected_tags"].to<JsonArray>();
  for (int index = 0; index < READER_COUNT; ++index) {
    const ReaderState& state = model_.readers[index];
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

void ProtocolModule::sendSwitchAcknowledgement(const SwitchMovedEvent& moved) {
  JsonDocument document;
  document["event"] = "move_ack";
  document["hub"] = HUB_ID;
  document["switch"] = SWITCHES[moved.switchIndex].id;
  document["angle"] = moved.angle;
  document["ok"] = moved.ok;
  document["request_id"] = moved.requestId;
  sendJson(document);
}

void ProtocolModule::sendTagChange(const TagChangedEvent& changed) {
  char tagId[3 * sizeof(changed.uid)] = {0};
  formatUid(changed.uid, changed.uidLength, tagId, sizeof(tagId));

  JsonDocument document;
  document["event"] = changed.detected ? "tag_detected" : "tag_removed";
  document["hub"] = HUB_ID;
  document["detector"] = READERS[changed.readerIndex].id;
  document["tag_id"] = tagId;
  sendJson(document);
}

void ProtocolModule::sendPong() {
  JsonDocument document;
  document["event"] = "pong";
  document["hub"] = HUB_ID;
  sendJson(document);
}

void ProtocolModule::sendJson(JsonDocument& document) {
  bus_.publish(OutboundDocumentEvent(document));
}

void ProtocolModule::formatUid(
    const uint8_t* uid,
    uint8_t uidLength,
    char* output,
    size_t size) {
  size_t offset = 0;
  for (uint8_t index = 0;
       index < uidLength && offset + 3 < size;
       ++index) {
    if (index > 0) output[offset++] = ':';
    offset += snprintf(output + offset, size - offset, "%02X", uid[index]);
  }
  output[offset] = '\0';
}

}  // namespace train
