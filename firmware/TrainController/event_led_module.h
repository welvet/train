#ifndef TRAIN_CONTROLLER_EVENT_LED_MODULE_H
#define TRAIN_CONTROLLER_EVENT_LED_MODULE_H

#include "event_bus.h"
#include "generated_config.h"
#include "model.h"
#include "module.h"

namespace train {

class EventLedModule : public Module {
 public:
  static constexpr unsigned long kBlipMs = 50;

  EventLedModule(
      EventBus& bus,
      ControllerModel& model,
      bool enabled = EVENT_LOGGER_ENABLED)
      : bus_(bus), model_(model), enabled_(enabled) {}

  bool setup() override;
  void trigger() override;

 private:
  EventBus& bus_;
  ControllerModel& model_;
  bool enabled_;
  bool lit_ = false;
  unsigned long litAt_ = 0;

  static void receive(void* context, const Event& event);
  void onEvent(const Event& event);
  void blip();
};

}  // namespace train

#endif
