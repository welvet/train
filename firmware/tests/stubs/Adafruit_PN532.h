#ifndef FIRMWARE_TEST_ADAFRUIT_PN532_H
#define FIRMWARE_TEST_ADAFRUIT_PN532_H

#include <Arduino.h>
#include <SPI.h>

#include <algorithm>
#include <cstdint>
#include <deque>
#include <initializer_list>
#include <vector>

constexpr uint8_t PN532_MIFARE_ISO14443A = 0;

namespace fake_pn532 {

struct Read {
  bool detected = false;
  std::vector<uint8_t> uid;
};

struct Device {
  uint32_t firmwareVersion = 1;
  bool samConfigured = true;
  bool began = false;
  std::deque<Read> reads;
};

inline std::vector<Device> devices;
inline size_t nextDevice = 0;

inline void reset(size_t count = 2) {
  devices.assign(count, Device{});
  nextDevice = 0;
  SPI.began = false;
}

inline void queueRead(size_t index, std::initializer_list<uint8_t> uid) {
  devices.at(index).reads.push_back({true, uid});
}

inline void queueMiss(size_t index) {
  devices.at(index).reads.push_back({false, {}});
}

}  // namespace fake_pn532

class Adafruit_PN532 {
 public:
  Adafruit_PN532(uint8_t, SPIClass*) : index_(fake_pn532::nextDevice++) {
    if (fake_pn532::devices.size() <= index_) {
      fake_pn532::devices.resize(index_ + 1);
    }
  }

  void begin() { fake_pn532::devices[index_].began = true; }

  uint32_t getFirmwareVersion() {
    return fake_pn532::devices[index_].firmwareVersion;
  }

  bool SAMConfig() { return fake_pn532::devices[index_].samConfigured; }

  bool readPassiveTargetID(
      uint8_t,
      uint8_t* uid,
      uint8_t* uidLength,
      uint16_t) {
    fake_pn532::Device& device = fake_pn532::devices[index_];
    if (device.reads.empty()) return false;
    fake_pn532::Read read = device.reads.front();
    device.reads.pop_front();
    if (!read.detected) return false;
    *uidLength = static_cast<uint8_t>(read.uid.size());
    std::copy(read.uid.begin(), read.uid.end(), uid);
    return true;
  }

 private:
  size_t index_;
};

#endif
