#ifndef FIRMWARE_TEST_SERVO_H
#define FIRMWARE_TEST_SERVO_H

#include <Arduino.h>

#include <array>

namespace fake_servo {

struct State {
  bool attached = false;
  int angle = 0;
  int attachCount = 0;
  int detachCount = 0;
};

inline std::array<State, 256> pins;

inline void reset() { pins = {}; }

}  // namespace fake_servo

class Servo {
 public:
  uint8_t attach(int pin) {
    pin_ = pin;
    fake_servo::State& state = fake_servo::pins[pin];
    state.attached = true;
    ++state.attachCount;
    return 1;
  }

  void write(int angle) { fake_servo::pins[pin_].angle = angle; }

  void detach() {
    if (pin_ < 0) return;
    fake_servo::State& state = fake_servo::pins[pin_];
    state.attached = false;
    ++state.detachCount;
  }

 private:
  int pin_ = -1;
};

#endif
