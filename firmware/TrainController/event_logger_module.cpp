#include "event_logger_module.h"

namespace train {

bool EventLoggerModule::setup() {
  return !enabled_ || bus_.subscribe(allEventsMask(), this, receive);
}

void EventLoggerModule::receive(void*, const Event& event) {
  Serial.print("event: ");
  Serial.println(eventName(event.type()));
}

const char* EventLoggerModule::eventName(EventType type) {
  switch (type) {
    case EventType::WifiConnected:
      return "wifi_connected";
    case EventType::WifiDisconnected:
      return "wifi_disconnected";
    case EventType::BackendConnected:
      return "backend_connected";
    case EventType::BackendDisconnected:
      return "backend_disconnected";
    case EventType::InboundLine:
      return "inbound_line";
    case EventType::InboundFrameTooLarge:
      return "inbound_frame_too_large";
    case EventType::OutboundDocument:
      return "outbound_document";
    case EventType::MoveSwitchRequested:
      return "move_switch_requested";
    case EventType::SwitchMoved:
      return "switch_moved";
    case EventType::TagChanged:
      return "tag_changed";
    case EventType::ConfigurationChanged:
      return "configuration_changed";
    case EventType::HardwareConfigured:
      return "hardware_configured";
    case EventType::DisconnectRequested:
      return "disconnect_requested";
    case EventType::Count:
      return "unknown";
  }
  return "unknown";
}

}  // namespace train
