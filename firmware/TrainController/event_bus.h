#ifndef TRAIN_CONTROLLER_EVENT_BUS_H
#define TRAIN_CONTROLLER_EVENT_BUS_H

#include "events.h"

namespace train {

using EventMask = uint16_t;

constexpr EventMask eventMask(EventType type) {
  return static_cast<EventMask>(1) << static_cast<uint8_t>(type);
}

constexpr EventMask allEventsMask() {
  return eventMask(EventType::Count) - 1;
}

static_assert(
    static_cast<uint8_t>(EventType::Count) < sizeof(EventMask) * 8,
    "EventMask needs one bit for every event type");

class EventBus {
 public:
  using Handler = void (*)(void* context, const Event& event);
  static constexpr uint8_t kMaxSubscribers = 8;

  bool subscribe(EventMask events, void* context, Handler handler);
  void publish(const Event& event);

 private:
  struct Subscriber {
    EventMask events;
    void* context;
    Handler handler;
  };

  Subscriber subscribers_[kMaxSubscribers];
  uint8_t subscriberCount_ = 0;

};

}  // namespace train

#endif
