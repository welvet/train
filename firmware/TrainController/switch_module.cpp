#include "switch_module.h"

#include <string.h>

namespace train {

bool SwitchModule::setup() {
  return bus_.subscribe(
      eventMask(EventType::MoveSwitchRequested), this, receive);
}

void SwitchModule::trigger() {
  const unsigned long now = millis();
  for (int index = 0; index < SWITCH_COUNT; ++index) {
    SwitchState& state = model_.switches[index];
    if (state.active && now - state.startedAt >= SERVO_SETTLE_MS) {
      servos_[index].detach();
      state.active = false;
    }
  }
}

void SwitchModule::receive(void* context, const Event& event) {
  static_cast<SwitchModule*>(context)->move(
      static_cast<const MoveSwitchRequestedEvent&>(event));
}

void SwitchModule::move(const MoveSwitchRequestedEvent& request) {
  const int index = findSwitch(request.switchId);
  if (index < 0) return;

  int angle = 0;
  const bool ok = resolveAngle(index, request, angle);
  if (ok) {
    servos_[index].attach(SWITCHES[index].pin);
    servos_[index].write(angle);
    model_.switches[index].active = true;
    model_.switches[index].startedAt = millis();
  }
  bus_.publish(SwitchMovedEvent(index, angle, ok));
}

int SwitchModule::findSwitch(const char* id) {
  for (int index = 0; index < SWITCH_COUNT; ++index) {
    if (strcmp(SWITCHES[index].id, id) == 0) return index;
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
    angle = SWITCHES[index].straightAngle;
    return true;
  }
  if (strcmp(request.position, "diverge") == 0) {
    angle = SWITCHES[index].divergeAngle;
    return true;
  }
  return false;
}

}  // namespace train
