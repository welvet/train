#ifndef TRAIN_CONTROLLER_CONFIG_TYPES_H
#define TRAIN_CONTROLLER_CONFIG_TYPES_H

#include <Arduino.h>

constexpr uint8_t CONFIG_SCHEMA = 1;
constexpr size_t MAX_ID_BYTES = 16;
constexpr size_t CONFIG_REVISION_BYTES = 64;
constexpr int MAX_SWITCHES = 8;
constexpr int MAX_READERS = 8;
constexpr int MAX_READER_TIMEOUT_TOTAL_MS = 1000;
constexpr int MIN_COMPONENT_PIN = 2;
constexpr int MAX_COMPONENT_PIN = 10;
constexpr size_t MAX_CONFIG_FRAME_BYTES = 2048;

struct SwitchConfig {
  char id[MAX_ID_BYTES + 1] = {0};
  uint8_t pin;
  int straightAngle;
  int divergeAngle;
};

struct ReaderConfig {
  char id[MAX_ID_BYTES + 1] = {0};
  uint8_t ssPin;
  uint16_t readTimeoutMs;
  unsigned long removalDelayMs;
};

struct RuntimeConfig {
  char hubId[MAX_ID_BYTES + 1] = {0};
  char revision[CONFIG_REVISION_BYTES + 1] = {0};
  unsigned long servoSettleMs = 0;
  int switchCount = 0;
  int readerCount = 0;
  SwitchConfig switches[MAX_SWITCHES];
  ReaderConfig readers[MAX_READERS];
};

#endif
