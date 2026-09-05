#include "event_led_module.h"

namespace train {

bool EventLedModule::setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);
  return bus_.subscribe(allEventsMask(), this, receive);
}

void EventLedModule::trigger() {
  if (lit_ && millis() - litAt_ >= kBlipMs) {
    digitalWrite(LED_BUILTIN, HIGH);
    lit_ = false;
  }
}

void EventLedModule::receive(void* context, const Event& event) {
  static_cast<EventLedModule*>(context)->onEvent(event);
}

void EventLedModule::onEvent(const Event& event) {
  if (event.type() == EventType::ConfigurationChanged && model_.readersUseSpi) {
    digitalWrite(LED_BUILTIN, HIGH);
    lit_ = false;
    return;
  }
  if (!model_.readersUseSpi) blip();
}

void EventLedModule::blip() {
  digitalWrite(LED_BUILTIN, LOW);
  lit_ = true;
  litAt_ = millis();
}

}  // namespace train
