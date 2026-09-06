#include "protocol_module.h"

#include <string.h>

namespace train {

bool ProtocolModule::setup() {
  return bus_.subscribe(
      eventMask(EventType::BackendConnected) |
          eventMask(EventType::InboundLine) |
          eventMask(EventType::InboundFrameTooLarge) |
          eventMask(EventType::BackendDisconnected) |
          eventMask(EventType::HardwareConfigured) |
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
      sendConfigurationRequest();
      waitingForConfiguration_ = true;
      applyingConfiguration_ = false;
      phaseStartedAt_ = millis();
      break;
    case EventType::BackendDisconnected:
      waitingForConfiguration_ = false;
      applyingConfiguration_ = false;
      model_.configurationPending = false;
      break;
    case EventType::HardwareConfigured:
      applyingConfiguration_ = false;
      sendHello();
      break;
    case EventType::InboundLine:
      handleLine(static_cast<const InboundLineEvent&>(event).value);
      break;
    case EventType::InboundFrameTooLarge:
      rejectConfiguration("frame_too_large");
      break;
    case EventType::SwitchMoved:
      if (!waitingForConfiguration_ && !applyingConfiguration_) {
        sendSwitchAcknowledgement(
            static_cast<const SwitchMovedEvent&>(event));
      }
      break;
    case EventType::TagChanged:
      if (!waitingForConfiguration_ && !applyingConfiguration_) {
        sendTagChange(static_cast<const TagChangedEvent&>(event));
      }
      break;
    default:
      break;
  }
}

void ProtocolModule::trigger() {
  const unsigned long elapsed = millis() - phaseStartedAt_;
  if (waitingForConfiguration_ && elapsed >= kConfigWaitTimeoutMs) {
    Serial.println("Configuration request timed out");
    bus_.publish(DisconnectRequestedEvent());
    waitingForConfiguration_ = false;
  } else if (applyingConfiguration_ && elapsed >= kConfigApplyTimeoutMs) {
    rejectConfiguration("apply_timeout");
  }
}

void ProtocolModule::handleLine(const char* line) {
  JsonDocument document;
  if (deserializeJson(document, line)) return;
  const char* command = document["cmd"];
  if (command == nullptr) return;

  if (strcmp(command, "configure") == 0) {
    if (!waitingForConfiguration_) {
      rejectConfiguration("unexpected_configuration");
      return;
    }
    RuntimeConfig staged;
    if (!parseConfiguration(document, staged)) {
      rejectConfiguration("invalid_configuration");
      return;
    }
    waitingForConfiguration_ = false;
    if (model_.configurationApplied &&
        strcmp(model_.config.revision, staged.revision) == 0) {
      sendHello();
      return;
    }
    applyConfiguration(staged);
  } else if (strcmp(command, "move") == 0) {
    if (!model_.configurationApplied) return;
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

bool ProtocolModule::parseConfiguration(
    JsonDocument& document, RuntimeConfig& config) {
  if (document["schema"] != CONFIG_SCHEMA ||
      !copyString(document["hub"], config.hubId, sizeof(config.hubId)) ||
      !copyString(
          document["revision"],
          config.revision,
          sizeof(config.revision),
          true) ||
      !document["servo_settle_ms"].is<unsigned long>()) {
    return false;
  }
  config.servoSettleMs = document["servo_settle_ms"];
  if (config.servoSettleMs == 0) return false;
  JsonArrayConst switches = document["switches"].as<JsonArrayConst>();
  JsonArrayConst readers = document["readers"].as<JsonArrayConst>();
  if (switches.isNull() || readers.isNull() ||
      switches.size() > MAX_SWITCHES || readers.size() > MAX_READERS) {
    return false;
  }
  bool pins[MAX_COMPONENT_PIN + 1] = {false};
  config.switchCount = static_cast<int>(switches.size());
  for (int index = 0; index < config.switchCount; ++index) {
    JsonObjectConst value = switches[index];
    SwitchConfig& item = config.switches[index];
    if (!copyString(value["id"], item.id, sizeof(item.id)) ||
        !value["pin"].is<int>() || !value["straight"].is<int>() ||
        !value["diverge"].is<int>()) return false;
    const int pin = value["pin"];
    item.straightAngle = value["straight"];
    item.divergeAngle = value["diverge"];
    if (pin < MIN_COMPONENT_PIN || pin > MAX_COMPONENT_PIN ||
        pins[pin] || item.straightAngle < 0 || item.straightAngle > 180 ||
        item.divergeAngle < 0 || item.divergeAngle > 180) return false;
    item.pin = static_cast<uint8_t>(pin);
    pins[pin] = true;
    for (int previous = 0; previous < index; ++previous) {
      if (strcmp(config.switches[previous].id, item.id) == 0) return false;
    }
  }
  config.readerCount = static_cast<int>(readers.size());
  for (int index = 0; index < config.readerCount; ++index) {
    JsonObjectConst value = readers[index];
    ReaderConfig& item = config.readers[index];
    if (!copyString(value["id"], item.id, sizeof(item.id)) ||
        !value["ss_pin"].is<int>() ||
        !value["read_timeout_ms"].is<int>() ||
        !value["removal_delay_ms"].is<unsigned long>()) return false;
    const int ssPin = value["ss_pin"];
    const int readTimeoutMs = value["read_timeout_ms"];
    item.removalDelayMs = value["removal_delay_ms"];
    if (ssPin < MIN_COMPONENT_PIN || ssPin > MAX_COMPONENT_PIN ||
        pins[ssPin] || readTimeoutMs <= 0 ||
        readTimeoutMs > 1000 || item.removalDelayMs == 0) return false;
    item.ssPin = static_cast<uint8_t>(ssPin);
    item.readTimeoutMs = static_cast<uint16_t>(readTimeoutMs);
    pins[ssPin] = true;
    for (int previous = 0; previous < config.switchCount; ++previous) {
      if (strcmp(config.switches[previous].id, item.id) == 0) return false;
    }
    for (int previous = 0; previous < index; ++previous) {
      if (strcmp(config.readers[previous].id, item.id) == 0) return false;
    }
  }
  return true;
}

void ProtocolModule::applyConfiguration(const RuntimeConfig& config) {
  model_.configurationApplied = false;
  model_.configurationPending = true;
  model_.config = config;
  model_.readersUseSpi = config.readerCount > 0;
  applyingConfiguration_ = true;
  phaseStartedAt_ = millis();
  bus_.publish(ConfigurationChangedEvent());
}

void ProtocolModule::sendConfigurationRequest() {
  JsonDocument document;
  document["event"] = "config_request";
  document["schema"] = CONFIG_SCHEMA;
  document["device_id"] = DEVICE_ID;
  sendJson(document);
}

void ProtocolModule::rejectConfiguration(const char* reason) {
  JsonDocument document;
  document["event"] = "config_rejected";
  document["schema"] = CONFIG_SCHEMA;
  document["device_id"] = DEVICE_ID;
  document["reason"] = reason;
  sendJson(document);
  waitingForConfiguration_ = false;
  applyingConfiguration_ = false;
  model_.configurationPending = false;
  bus_.publish(DisconnectRequestedEvent());
}

void ProtocolModule::sendHello() {
  JsonDocument document;
  document["event"] = "hello";
  document["hub"] = model_.config.hubId;
  document["revision"] = model_.config.revision;
  JsonObject applied = document["applied"].to<JsonObject>();
  applied["schema"] = CONFIG_SCHEMA;
  applied["hub"] = model_.config.hubId;
  applied["servo_settle_ms"] = model_.config.servoSettleMs;
  JsonArray appliedSwitches = applied["switches"].to<JsonArray>();
  for (int index = 0; index < model_.config.switchCount; ++index) {
    const SwitchConfig& config = model_.config.switches[index];
    JsonObject value = appliedSwitches.add<JsonObject>();
    value["id"] = config.id;
    value["pin"] = config.pin;
    value["straight"] = config.straightAngle;
    value["diverge"] = config.divergeAngle;
  }
  JsonArray appliedReaders = applied["readers"].to<JsonArray>();
  for (int index = 0; index < model_.config.readerCount; ++index) {
    const ReaderConfig& config = model_.config.readers[index];
    JsonObject value = appliedReaders.add<JsonObject>();
    value["id"] = config.id;
    value["ss_pin"] = config.ssPin;
    value["read_timeout_ms"] = config.readTimeoutMs;
    value["removal_delay_ms"] = config.removalDelayMs;
  }
  JsonArray switches = document["switches"].to<JsonArray>();
  for (int index = 0; index < model_.config.switchCount; ++index) {
    switches.add(model_.config.switches[index].id);
  }

  JsonArray detectors = document["detectors"].to<JsonArray>();
  JsonArray detectedTags = document["detected_tags"].to<JsonArray>();
  for (int index = 0; index < model_.config.readerCount; ++index) {
    const ReaderState& state = model_.readers[index];
    if (!state.ready) continue;
    detectors.add(model_.config.readers[index].id);
    if (state.tagPresent) {
      char tagId[3 * sizeof(state.uid)] = {0};
      formatUid(state.uid, state.uidLength, tagId, sizeof(tagId));
      JsonObject tag = detectedTags.add<JsonObject>();
      tag["detector"] = model_.config.readers[index].id;
      tag["tag_id"] = tagId;
    }
  }
  sendJson(document);
}

void ProtocolModule::sendSwitchAcknowledgement(const SwitchMovedEvent& moved) {
  JsonDocument document;
  document["event"] = "move_ack";
  document["hub"] = model_.config.hubId;
  document["switch"] = model_.config.switches[moved.switchIndex].id;
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
  document["hub"] = model_.config.hubId;
  document["detector"] = model_.config.readers[changed.readerIndex].id;
  document["tag_id"] = tagId;
  sendJson(document);
}

void ProtocolModule::sendPong() {
  JsonDocument document;
  document["event"] = "pong";
  if (model_.configurationApplied) document["hub"] = model_.config.hubId;
  else document["device_id"] = DEVICE_ID;
  sendJson(document);
}

void ProtocolModule::sendJson(JsonDocument& document) {
  bus_.publish(OutboundDocumentEvent(document));
}

bool ProtocolModule::copyString(
    JsonVariantConst value,
    char* output,
    size_t capacity,
    bool hex) {
  if (!value.is<const char*>()) return false;
  const char* input = value.as<const char*>();
  const size_t length = strlen(input);
  if (length == 0 || length >= capacity) return false;
  if (hex && length != CONFIG_REVISION_BYTES) return false;
  for (size_t index = 0; index < length; ++index) {
    const char character = input[index];
    if (hex && !((character >= '0' && character <= '9') ||
                 (character >= 'a' && character <= 'f'))) return false;
  }
  memcpy(output, input, length + 1);
  return true;
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
