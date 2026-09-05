#include "wifi_module.h"

namespace train {

bool WifiModule::setup() {
  connect();
  return true;
}

void WifiModule::trigger() {
  const bool connected = WiFi.status() == WL_CONNECTED;
  if (connected != model_.wifiConnected) {
    model_.wifiConnected = connected;
    if (connected) {
      bus_.publish(WifiConnectedEvent());
    } else {
      bus_.publish(WifiDisconnectedEvent());
    }
  }

  if (!connected && millis() - lastConnectAttempt_ >= RECONNECT_MS) connect();
}

void WifiModule::connect() {
  lastConnectAttempt_ = millis();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

}  // namespace train
