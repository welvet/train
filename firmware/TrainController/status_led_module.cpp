#include "status_led_module.h"

namespace train {

bool StatusLedModule::setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  return true;
}

void StatusLedModule::trigger() {
  digitalWrite(
      LED_BUILTIN,
      model_.backendConnected || (millis() / 150) % 2 == 0 ? LOW : HIGH);
}

}  // namespace train
