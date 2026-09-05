#ifndef TRAIN_CONTROLLER_PROTOCOL_MODULE_H
#define TRAIN_CONTROLLER_PROTOCOL_MODULE_H

#include <ArduinoJson.h>

#include "event_bus.h"
#include "model.h"
#include "module.h"

namespace train {

class ProtocolModule : public Module {
 public:
  ProtocolModule(EventBus& bus, ControllerModel& model)
      : bus_(bus), model_(model) {}

  bool setup() override;
  void trigger() override {}

 private:
  EventBus& bus_;
  ControllerModel& model_;

  static void receive(void* context, const Event& event);
  void onEvent(const Event& event);
  void handleLine(const char* line);
  void sendHello();
  void sendSwitchAcknowledgement(const SwitchMovedEvent& moved);
  void sendTagChange(const TagChangedEvent& changed);
  void sendPong();
  void sendJson(JsonDocument& document);
  static void formatUid(
      const uint8_t* uid,
      uint8_t uidLength,
      char* output,
      size_t size);
};

}  // namespace train

#endif
