#ifndef TRAIN_CONTROLLER_STATUS_LED_MODULE_H
#define TRAIN_CONTROLLER_STATUS_LED_MODULE_H

#include "model.h"
#include "module.h"

namespace train {

class StatusLedModule : public Module {
 public:
  explicit StatusLedModule(ControllerModel& model) : model_(model) {}

  bool setup() override;
  void trigger() override;

 private:
  ControllerModel& model_;
};

}  // namespace train

#endif
