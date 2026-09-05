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
  Adafruit_PN532* readers_[READER_STORAGE_SIZE] = {nullptr};
  int nextReaderIndex_ = 0;

  void updateReader(int index);
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
