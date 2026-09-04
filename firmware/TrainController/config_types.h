#ifndef TRAIN_CONTROLLER_CONFIG_TYPES_H
#define TRAIN_CONTROLLER_CONFIG_TYPES_H

#include <Arduino.h>

struct SwitchConfig {
  const char* id;
  uint8_t pin;
  int straightAngle;
  int divergeAngle;
};

struct ReaderConfig {
  const char* id;
  uint8_t ssPin;
  uint16_t readTimeoutMs;
  unsigned long removalDelayMs;
};

#endif
