#ifndef TRAIN_CONTROLLER_MODEL_H
#define TRAIN_CONTROLLER_MODEL_H

#include <Arduino.h>

#include "generated_config.h"

namespace train {

struct ReaderState {
  bool ready = false;
  bool tagPresent = false;
  uint8_t uid[7] = {0};
  uint8_t uidLength = 0;
  unsigned long lastSeenAt = 0;
};

struct SwitchState {
  bool active = false;
  unsigned long startedAt = 0;
};

struct ControllerModel {
  bool wifiConnected = false;
  bool backendConnected = false;
  ReaderState readers[READER_STORAGE_SIZE];
  SwitchState switches[SWITCH_STORAGE_SIZE];
};

}  // namespace train

#endif
