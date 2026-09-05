#include "switch_module.h"

#include <string.h>

namespace train {

bool SwitchModule::setup() {
  return bus_.subscribe(
      eventMask(EventType::MoveSwitchRequested) |
          eventMask(EventType::ConfigurationChanged),
      this,
      receive);
}

void SwitchModule::trigger() {
  const unsigned long now = millis();
  for (int index = 0; index < model_.config.switchCount; ++index) {
    SwitchState& state = model_.switches[index];
    if (state.active &&
        now - state.startedAt >= model_.config.servoSettleMs) {
      servos_[index].detach();
      state.active = false;
    }
  }
}

void SwitchModule::receive(void* context, const Event& event) {
  SwitchModule* module = static_cast<SwitchModule*>(context);
  if (event.type() == EventType::ConfigurationChanged) {
    module->reset();
  } else {
    module->move(static_cast<const MoveSwitchRequestedEvent&>(event));
  }
}

void SwitchModule::move(const MoveSwitchRequestedEvent& request) {
  const int index = findSwitch(request.switchId);
  if (index < 0) return;

  int angle = 0;
  const bool ok = resolveAngle(index, request, angle);
  if (ok) {
    const int attached = servos_[index].attach(model_.config.switches[index].pin);
    if (attached != 0) {
      servos_[index].write(angle);
      model_.switches[index].active = true;
      model_.switches[index].startedAt = millis();
    } else {
      bus_.publish(SwitchMovedEvent(index, angle, false, request.requestId));
      return;
    }
  }
  bus_.publish(SwitchMovedEvent(index, angle, ok, request.requestId));
}

int SwitchModule::findSwitch(const char* id) const {
  for (int index = 0; index < model_.config.switchCount; ++index) {
    if (strcmp(model_.config.switches[index].id, id) == 0) return index;
  }
  return -1;
}

bool SwitchModule::resolveAngle(
    int index,
    const MoveSwitchRequestedEvent& request,
    int& angle) {
  if (request.hasAngle) {
    angle = request.angle;
    return angle >= 0 && angle <= 180;
  }
  if (request.position == nullptr) return false;
  if (strcmp(request.position, "straight") == 0) {
    angle = model_.config.switches[index].straightAngle;
    return true;
  }
  if (strcmp(request.position, "diverge") == 0) {
    angle = model_.config.switches[index].divergeAngle;
    return true;
  }
  return false;
}

void SwitchModule::reset() {
  for (int index = 0; index < MAX_SWITCHES; ++index) {
    servos_[index].detach();
    model_.switches[index] = {};
  }
}

}  // namespace train
