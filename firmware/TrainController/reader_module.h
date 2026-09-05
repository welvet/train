#ifndef TRAIN_CONTROLLER_READER_MODULE_H
#define TRAIN_CONTROLLER_READER_MODULE_H

#include <Adafruit_PN532.h>
#include <SPI.h>

#include "event_bus.h"
#include "model.h"
#include "module.h"

namespace train {

class ReaderModule : public Module {
 public:
  ReaderModule(EventBus& bus, ControllerModel& model)
      : bus_(bus), model_(model) {}

  bool setup() override;
  void trigger() override;

 private:
  EventBus& bus_;
  ControllerModel& model_;
  static constexpr int kPinSlots = MAX_COMPONENT_PIN - MIN_COMPONENT_PIN + 1;
  Adafruit_PN532* readers_[MAX_READERS] = {nullptr};
  Adafruit_PN532* pinCache_[kPinSlots] = {nullptr};
  int nextReaderIndex_ = 0;
  int provisioningIndex_ = 0;

  static void receive(void* context, const Event& event);
  void beginConfiguration();
  void provisionNextReader();
  void updateReader(int index);
  void scanReader(int index, bool publish);
  void publishChange(int index, bool detected);
  static bool uidMatches(
      const ReaderState& state,
      const uint8_t* uid,
      uint8_t length);
  static void rememberUid(
      ReaderState& state,
      const uint8_t* uid,
      uint8_t length);
};

}  // namespace train

#endif
