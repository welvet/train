#ifndef CONFIG_H
#define CONFIG_H

#define HUB_NAME "A_HUB_1"

struct SwitchConfig {
  const char* name;
  int pin;
  int angleStraight;
  int angleDiverge;
};

const int NUM_SWITCHES = 2;
const SwitchConfig SWITCHES[NUM_SWITCHES] = {
  { "S1", 9,  58, 100 },
  { "S2", 10, 58, 100 },
};
const unsigned long SERVO_SETTLE_MS = 500;

// PN532 train-tag detector. Hardware SPI uses D13/SCK, D12/MISO, D11/MOSI.
#define DETECTOR_NAME "D1"
const uint8_t PN532_SS_PIN = 4;
const uint16_t TAG_READ_TIMEOUT_MS = 250;
const unsigned long TAG_REMOVAL_DELAY_MS = 750;

// Backend TCP server
#define BACKEND_HOST "192.168.50.80"
#define BACKEND_PORT 9000
#define RECONNECT_MS 2000

#endif
