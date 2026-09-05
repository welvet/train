#ifndef FIRMWARE_TEST_ARDUINO_H
#define FIRMWARE_TEST_ARDUINO_H

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

using std::min;

constexpr uint8_t LOW = 0;
constexpr uint8_t HIGH = 1;
constexpr uint8_t OUTPUT = 1;
constexpr uint8_t LED_BUILTIN = 13;

namespace fake_arduino {

struct PinWrite {
  uint8_t pin;
  uint8_t value;
};

inline unsigned long now = 0;
inline std::vector<std::pair<uint8_t, uint8_t>> pinModes;
inline std::vector<PinWrite> pinWrites;

inline void reset() {
  now = 0;
  pinModes.clear();
  pinWrites.clear();
}

}  // namespace fake_arduino

inline unsigned long millis() { return fake_arduino::now; }

inline void pinMode(uint8_t pin, uint8_t mode) {
  fake_arduino::pinModes.emplace_back(pin, mode);
}

inline void digitalWrite(uint8_t pin, uint8_t value) {
  fake_arduino::pinWrites.push_back({pin, value});
}

class HardwareSerial {
 public:
  void begin(unsigned long) {}

  template <typename Value>
  void print(const Value&) {}

  template <typename Value>
  void println(const Value&) {}
};

inline HardwareSerial Serial;

#endif
