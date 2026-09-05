#include "event_bus.h"

namespace train {

bool EventBus::subscribe(EventMask events, void* context, Handler handler) {
  if (events == 0 || handler == nullptr || subscriberCount_ >= kMaxSubscribers) {
    return false;
  }
  for (uint8_t index = 0; index < subscriberCount_; ++index) {
    if (subscribers_[index].context == context) return false;
  }
  subscribers_[subscriberCount_++] = {events, context, handler};
  return true;
}

void EventBus::publish(const Event& event) {
  const uint8_t subscriberCount = subscriberCount_;
  for (uint8_t index = 0; index < subscriberCount; ++index) {
    const Subscriber& subscriber = subscribers_[index];
    if ((subscriber.events & eventMask(event.type())) != 0) {
      subscriber.handler(subscriber.context, event);
    }
  }
}

}  // namespace train
