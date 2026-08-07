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

struct DetectorConfig {
  const char* name;
  int pin;
  bool activeLow;
};

const int NUM_DETECTORS = 2;
const DetectorConfig DETECTORS[NUM_DETECTORS] = {
  { "D1", 2, true },
  { "D2", 3, true },
};

// Backend TCP server
#define BACKEND_HOST "192.168.50.186"
#define BACKEND_PORT 9000
#define RECONNECT_MS 2000

#endif
