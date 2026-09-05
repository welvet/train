#ifndef TRAIN_CONTROLLER_EVENT_LED_MODULE_H
#define TRAIN_CONTROLLER_EVENT_LED_MODULE_H

#include "event_bus.h"
#include "module.h"

namespace train {

class EventLedModule : public Module {
 public:
  static constexpr unsigned long kBlipMs = 50;

  explicit EventLedModule(EventBus& bus) : bus_(bus) {}

  bool setup() override;
  void trigger() override;

 private:
  EventBus& bus_;
  bool lit_ = false;
  unsigned long litAt_ = 0;

  static void receive(void* context, const Event& event);
  void blip();
};

}  // namespace train

#endif
