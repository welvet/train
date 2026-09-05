#ifndef GENERATED_CONFIG_H
#define GENERATED_CONFIG_H

#include "config_types.h"

constexpr char HUB_ID[] = "test-hub";
constexpr char BACKEND_HOST[] = "backend.test";
constexpr uint16_t BACKEND_PORT = 9000;
constexpr char WIFI_SSID[] = "test-wifi";
constexpr char WIFI_PASSWORD[] = "test-password";
constexpr unsigned long SERIAL_BAUDRATE = 115200;
constexpr unsigned long SERVO_SETTLE_MS = 500;
constexpr unsigned long RECONNECT_MS = 2000;
constexpr bool EVENT_LOGGER_ENABLED = false;

constexpr int SWITCH_COUNT = 2;
constexpr int SWITCH_STORAGE_SIZE = 2;
const SwitchConfig SWITCHES[SWITCH_STORAGE_SIZE] = {
    {"S1", 9, 55, 105},
    {"S2", 10, 60, 110},
};

constexpr int READER_COUNT = 2;
constexpr int READER_STORAGE_SIZE = 2;
const ReaderConfig READERS[READER_STORAGE_SIZE] = {
    {"D1", 4, 25, 750},
    {"D2", 5, 25, 1000},
};

#endif
