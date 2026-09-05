#ifndef TRAIN_CONTROLLER_TRANSPORT_MODULE_H
#define TRAIN_CONTROLLER_TRANSPORT_MODULE_H

#include <WiFiS3.h>

#include "event_bus.h"
#include "model.h"
#include "module.h"

namespace train {

class TransportModule : public Module {
 public:
  TransportModule(EventBus& bus, ControllerModel& model)
      : bus_(bus), model_(model) {}

  bool setup() override;
  void trigger() override;

 private:
  static constexpr size_t kLineBufferSize = 256;

  EventBus& bus_;
  ControllerModel& model_;
  WiFiClient client_;
  unsigned long lastConnectAttempt_ = 0;
  bool connectImmediately_ = false;
  char lineBuffer_[kLineBufferSize] = {0};
  size_t lineLength_ = 0;
  bool lineOverflowed_ = false;

  static void receive(void* context, const Event& event);
  void onEvent(const Event& event);
  void updateConnection();
  void readLines();
  void setBackendConnected(bool connected);
};

}  // namespace train

#endif
