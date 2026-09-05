#ifndef FIRMWARE_TEST_WIFI_S3_H
#define FIRMWARE_TEST_WIFI_S3_H

#include <Arduino.h>

#include <cstdint>
#include <deque>
#include <string>

constexpr int WL_DISCONNECTED = 0;
constexpr int WL_CONNECTED = 3;

namespace fake_wifi {

struct WifiState {
  int status = WL_DISCONNECTED;
  int beginCount = 0;
  std::string ssid;
  std::string password;
};

struct ClientState {
  bool connected = false;
  bool connectSucceeds = true;
  int connectCount = 0;
  int stopCount = 0;
  std::string host;
  uint16_t port = 0;
  std::deque<char> input;
  std::string output;
};

inline WifiState wifi;
inline ClientState client;

inline void reset() {
  wifi = {};
  client = {};
  client.connectSucceeds = true;
}

inline void receive(const std::string& value) {
  client.input.insert(client.input.end(), value.begin(), value.end());
}

}  // namespace fake_wifi

class WiFiClass {
 public:
  int status() const { return fake_wifi::wifi.status; }

  void begin(const char* ssid, const char* password) {
    ++fake_wifi::wifi.beginCount;
    fake_wifi::wifi.ssid = ssid;
    fake_wifi::wifi.password = password;
  }
};

inline WiFiClass WiFi;

class WiFiClient {
 public:
  bool connected() const { return fake_wifi::client.connected; }

  bool connect(const char* host, uint16_t port) {
    ++fake_wifi::client.connectCount;
    fake_wifi::client.host = host;
    fake_wifi::client.port = port;
    fake_wifi::client.connected = fake_wifi::client.connectSucceeds;
    return fake_wifi::client.connected;
  }

  void stop() {
    ++fake_wifi::client.stopCount;
    fake_wifi::client.connected = false;
  }

  int available() const {
    return static_cast<int>(fake_wifi::client.input.size());
  }

  int read() {
    if (fake_wifi::client.input.empty()) return -1;
    const char value = fake_wifi::client.input.front();
    fake_wifi::client.input.pop_front();
    return value;
  }

  size_t write(uint8_t value) {
    fake_wifi::client.output.push_back(static_cast<char>(value));
    return 1;
  }

  size_t write(const uint8_t* values, size_t size) {
    fake_wifi::client.output.append(
        reinterpret_cast<const char*>(values), size);
    return size;
  }

  size_t println() {
    fake_wifi::client.output += "\r\n";
    return 2;
  }
};

#endif
