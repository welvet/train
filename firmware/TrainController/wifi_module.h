#ifndef TRAIN_CONTROLLER_WIFI_MODULE_H
#define TRAIN_CONTROLLER_WIFI_MODULE_H

#include <WiFiS3.h>

#include "event_bus.h"
#include "model.h"
#include "module.h"

namespace train {

class WifiModule : public Module {
 public:
  WifiModule(EventBus& bus, ControllerModel& model) : bus_(bus), model_(model) {}

  bool setup() override;
  void trigger() override;

 private:
  EventBus& bus_;
  ControllerModel& model_;
  unsigned long lastConnectAttempt_ = 0;

  void connect();
};

}  // namespace train

#endif
