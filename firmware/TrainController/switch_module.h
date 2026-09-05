#ifndef TRAIN_CONTROLLER_SWITCH_MODULE_H
#define TRAIN_CONTROLLER_SWITCH_MODULE_H

#include <Servo.h>

#include "event_bus.h"
#include "model.h"
#include "module.h"

namespace train {

class SwitchModule : public Module {
 public:
  SwitchModule(EventBus& bus, ControllerModel& model)
      : bus_(bus), model_(model) {}

  bool setup() override;
  void trigger() override;

 private:
  EventBus& bus_;
  ControllerModel& model_;
  Servo servos_[SWITCH_STORAGE_SIZE];

  static void receive(void* context, const Event& event);
  void move(const MoveSwitchRequestedEvent& request);
  static int findSwitch(const char* id);
  static bool resolveAngle(
      int index,
      const MoveSwitchRequestedEvent& request,
      int& angle);
};

}  // namespace train

#endif
