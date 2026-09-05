#include "transport_module.h"

namespace train {

bool TransportModule::setup() {
  return bus_.subscribe(
      eventMask(EventType::WifiConnected) |
          eventMask(EventType::WifiDisconnected) |
          eventMask(EventType::OutboundDocument),
      this,
      receive);
}

void TransportModule::trigger() {
  updateConnection();
  readLines();
}

void TransportModule::receive(void* context, const Event& event) {
  static_cast<TransportModule*>(context)->onEvent(event);
}

void TransportModule::onEvent(const Event& event) {
  if (event.type() == EventType::WifiConnected) {
    connectImmediately_ = true;
    return;
  }
  if (event.type() == EventType::WifiDisconnected) {
    client_.stop();
    setBackendConnected(false);
    return;
  }
  if (event.type() == EventType::OutboundDocument && client_.connected()) {
    const OutboundDocumentEvent& outbound =
        static_cast<const OutboundDocumentEvent&>(event);
    serializeJson(outbound.document, client_);
    client_.println();
  }
}

void TransportModule::updateConnection() {
  if (model_.backendConnected && !client_.connected()) {
    setBackendConnected(false);
  }
  if (!model_.wifiConnected || model_.backendConnected) return;

  const unsigned long now = millis();
  if (!connectImmediately_ && now - lastConnectAttempt_ < RECONNECT_MS) return;
  connectImmediately_ = false;
  lastConnectAttempt_ = now;
  if (client_.connect(BACKEND_HOST, BACKEND_PORT)) setBackendConnected(true);
}

void TransportModule::readLines() {
  while (client_.available()) {
    const char value = client_.read();
    if (value == '\n') {
      lineBuffer_[lineLength_] = '\0';
      if (lineLength_ > 0) {
        bus_.publish(InboundLineEvent(lineBuffer_));
      }
      lineLength_ = 0;
    } else if (lineLength_ < kLineBufferSize - 1) {
      lineBuffer_[lineLength_++] = value;
    }
  }
}

void TransportModule::setBackendConnected(bool connected) {
  if (model_.backendConnected == connected) return;
  model_.backendConnected = connected;
  lineLength_ = 0;
  if (connected) {
    bus_.publish(BackendConnectedEvent());
  } else {
    bus_.publish(BackendDisconnectedEvent());
  }
}

}  // namespace train
