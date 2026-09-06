#include "event_bus.h"
#include "event_led_module.h"
#include "event_logger_module.h"
#include "model.h"
#include "module.h"
#include "protocol_module.h"
#include "reader_module.h"
#include "switch_module.h"
#include "transport_module.h"
#include "wifi_module.h"

train::EventBus bus;
train::ControllerModel model;

train::EventLoggerModule eventLogger(bus);
train::EventLedModule eventLed(bus, model);
train::TransportModule transport(bus, model);
train::ProtocolModule protocol(bus, model);
train::SwitchModule switches(bus, model);
train::ReaderModule readers(bus, model);
train::WifiModule wifi(bus, model);

train::Module* modules[] = {
    &eventLogger,
    &eventLed,
    &transport,
    &protocol,
    &switches,
    &readers,
    &wifi,
};
constexpr size_t moduleCount = sizeof(modules) / sizeof(modules[0]);
static_assert(
    moduleCount <= train::EventBus::kMaxSubscribers,
    "EventBus needs capacity for every module");
bool controllerReady = false;

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  for (size_t index = 0; index < moduleCount; ++index) {
    if (!modules[index]->setup()) {
      Serial.print("Module setup failed at index ");
      Serial.println(index);
      return;
    }
  }
  controllerReady = true;
}

void loop() {
  if (!controllerReady) return;
  for (train::Module* module : modules) module->trigger();
}
