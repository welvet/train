#ifndef TEST_CONTROLLER_FIRMWARE_CONFIG_H
#define TEST_CONTROLLER_FIRMWARE_CONFIG_H

#include <Arduino.h>

// Increment this when changing the firmware so serial logs identify the build.
constexpr char FIRMWARE_NAME[] = "PN532 Reader Test";
constexpr char FIRMWARE_VERSION[] = "0.1.0";

// PN532 hardware SPI wiring on the Arduino UNO R4 WiFi:
// SCK=D13, MOSI=D11, MISO=D12, SS=D4.
constexpr uint8_t PN532_SS_PIN = 4;

constexpr unsigned long SERIAL_BAUD_RATE = 115200;
constexpr uint16_t READ_TIMEOUT_MS = 250;
constexpr unsigned long TAG_REMOVAL_DELAY_MS = 750;
constexpr unsigned long POLL_HEARTBEAT_INTERVAL_MS = 5000;

#endif
