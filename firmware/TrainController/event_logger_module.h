#ifndef TRAIN_CONTROLLER_EVENT_LOGGER_MODULE_H
#define TRAIN_CONTROLLER_EVENT_LOGGER_MODULE_H

#include "event_bus.h"
#include "generated_config.h"
#include "module.h"

namespace train {

class EventLoggerModule : public Module {
 public:
  explicit EventLoggerModule(
      EventBus& bus,
      bool enabled = EVENT_LOGGER_ENABLED)
      : bus_(bus), enabled_(enabled) {}

  bool setup() override;
  void trigger() override {}

 private:
  EventBus& bus_;
  bool enabled_;

  static void receive(void* context, const Event& event);
  static const char* eventName(EventType type);
};

}  // namespace train

#endif
