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

void EventLedModule::receive(void* context, const Event&) {
  static_cast<EventLedModule*>(context)->blip();
}

void EventLedModule::blip() {
  digitalWrite(LED_BUILTIN, LOW);
  lit_ = true;
  litAt_ = millis();
}

}  // namespace train
