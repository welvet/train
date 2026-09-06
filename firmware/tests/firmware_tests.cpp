#include <Adafruit_PN532.h>
#include <ArduinoJson.h>
#include <Servo.h>
#include <WiFiS3.h>

#include <climits>
#include <cstring>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "event_bus.h"
#include "event_led_module.h"
#include "event_logger_module.h"
#include "protocol_module.h"
#include "reader_module.h"
#include "switch_module.h"
#include "transport_module.h"
#include "wifi_module.h"

namespace {

using train::BackendConnectedEvent;
using train::BackendDisconnectedEvent;
using train::ControllerModel;
using train::Event;
using train::EventBus;
using train::EventType;
using train::InboundLineEvent;
using train::MoveSwitchRequestedEvent;
using train::OutboundDocumentEvent;
using train::SwitchMovedEvent;
using train::TagChangedEvent;
using train::WifiConnectedEvent;
using train::WifiDisconnectedEvent;

struct TestCase {
  const char* name;
  std::function<void()> run;
};

std::vector<TestCase>& tests() {
  static std::vector<TestCase> value;
  return value;
}

struct RegisterTest {
  RegisterTest(const char* name, std::function<void()> run) {
    tests().push_back({name, std::move(run)});
  }
};

#define TEST(name)                  \
  void name();                      \
  RegisterTest name##_registration(#name, name); \
  void name()

#define CHECK(condition)                                                     \
  do {                                                                       \
    if (!(condition)) {                                                       \
      throw std::runtime_error(                                               \
          std::string(__FILE__) + ":" + std::to_string(__LINE__) +           \
          ": CHECK failed: " #condition);                                    \
    }                                                                        \
  } while (false)

struct TypeCollector {
  std::vector<EventType> values;

  static void receive(void* context, const Event& event) {
    static_cast<TypeCollector*>(context)->values.push_back(event.type());
  }
};

struct JsonCollector {
  std::vector<std::string> values;

  static void receive(void* context, const Event& event) {
    auto& collector = *static_cast<JsonCollector*>(context);
    const auto& outbound = static_cast<const OutboundDocumentEvent&>(event);
    std::string value;
    serializeJson(outbound.document, value);
    collector.values.push_back(value);
  }
};

struct MoveCollector {
  struct Value {
    std::string switchId;
    bool hasAngle;
    int angle;
    std::string position;
    std::string requestId;
  };
  std::vector<Value> values;

  static void receive(void* context, const Event& event) {
    auto& collector = *static_cast<MoveCollector*>(context);
    const auto& move = static_cast<const MoveSwitchRequestedEvent&>(event);
    collector.values.push_back({
        move.switchId,
        move.hasAngle,
        move.angle,
        move.position == nullptr ? "" : move.position,
        move.requestId,
    });
  }
};

struct SwitchCollector {
  struct Value {
    int index;
    int angle;
    bool ok;
    std::string requestId;
  };
  std::vector<Value> values;

  static void receive(void* context, const Event& event) {
    auto& collector = *static_cast<SwitchCollector*>(context);
    const auto& moved = static_cast<const SwitchMovedEvent&>(event);
    collector.values.push_back({
        moved.switchIndex,
        moved.angle,
        moved.ok,
        moved.requestId,
    });
  }
};

struct TagCollector {
  struct Value {
    int index;
    bool detected;
    std::vector<uint8_t> uid;
  };
  std::vector<Value> values;

  static void receive(void* context, const Event& event) {
    auto& collector = *static_cast<TagCollector*>(context);
    const auto& changed = static_cast<const TagChangedEvent&>(event);
    collector.values.push_back({
        changed.readerIndex,
        changed.detected,
        {changed.uid, changed.uid + changed.uidLength},
    });
  }
};

struct LineCollector {
  std::vector<std::string> values;

  static void receive(void* context, const Event& event) {
    auto& collector = *static_cast<LineCollector*>(context);
    collector.values.emplace_back(static_cast<const InboundLineEvent&>(event).value);
  }
};

JsonDocument parseJson(const std::string& value) {
  JsonDocument document;
  CHECK(!deserializeJson(document, value));
  return document;
}

void resetFakes() {
  fake_arduino::reset();
  fake_servo::reset();
  fake_wifi::reset();
  fake_pn532::reset();
}

void configureTestModel(ControllerModel& model) {
  std::strcpy(model.config.hubId, "test-hub");
  std::strcpy(
      model.config.revision,
      "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
  model.config.servoSettleMs = 500;
  model.config.switchCount = 2;
  std::strcpy(model.config.switches[0].id, "S1");
  model.config.switches[0].pin = 9;
  model.config.switches[0].straightAngle = 55;
  model.config.switches[0].divergeAngle = 105;
  std::strcpy(model.config.switches[1].id, "S2");
  model.config.switches[1].pin = 10;
  model.config.switches[1].straightAngle = 60;
  model.config.switches[1].divergeAngle = 110;
  model.config.readerCount = 2;
  std::strcpy(model.config.readers[0].id, "D1");
  model.config.readers[0].ssPin = 4;
  model.config.readers[0].readTimeoutMs = 25;
  model.config.readers[0].removalDelayMs = 750;
  std::strcpy(model.config.readers[1].id, "D2");
  model.config.readers[1].ssPin = 5;
  model.config.readers[1].readTimeoutMs = 25;
  model.config.readers[1].removalDelayMs = 1000;
}

TEST(eventBusFiltersEventsAndRejectsDuplicateContexts) {
  EventBus bus;
  TypeCollector collector;

  CHECK(bus.subscribe(
      train::eventMask(EventType::WifiConnected),
      &collector,
      TypeCollector::receive));
  CHECK(!bus.subscribe(
      train::eventMask(EventType::WifiDisconnected),
      &collector,
      TypeCollector::receive));

  bus.publish(WifiDisconnectedEvent());
  bus.publish(WifiConnectedEvent());

  CHECK(collector.values.size() == 1);
  CHECK(collector.values[0] == EventType::WifiConnected);
}

TEST(eventBusRejectsInvalidAndExcessSubscriptions) {
  EventBus bus;
  TypeCollector collectors[EventBus::kMaxSubscribers + 1];

  CHECK(!bus.subscribe(0, &collectors[0], TypeCollector::receive));
  CHECK(!bus.subscribe(
      train::eventMask(EventType::WifiConnected), &collectors[0], nullptr));
  for (uint8_t index = 0; index < EventBus::kMaxSubscribers; ++index) {
    CHECK(bus.subscribe(
        train::eventMask(EventType::WifiConnected),
        &collectors[index],
        TypeCollector::receive));
  }
  CHECK(!bus.subscribe(
      train::eventMask(EventType::WifiConnected),
      &collectors[EventBus::kMaxSubscribers],
      TypeCollector::receive));
}

TEST(protocolSendsCompleteHelloSnapshot) {
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  model.configurationApplied = true;
  model.readers[0].ready = true;
  model.readers[0].tagPresent = true;
  model.readers[0].uid[0] = 0x04;
  model.readers[0].uid[1] = 0xA1;
  model.readers[0].uidLength = 2;
  model.readers[1].ready = false;
  train::ProtocolModule protocol(bus, model);
  JsonCollector output;

  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::OutboundDocument),
      &output,
      JsonCollector::receive));
  bus.publish(train::HardwareConfiguredEvent());

  CHECK(output.values.size() == 1);
  JsonDocument document = parseJson(output.values[0]);
  CHECK(document["event"] == "hello");
  CHECK(document["hub"] == "test-hub");
  CHECK(document["switches"].size() == 2);
  CHECK(document["switches"][0] == "S1");
  CHECK(document["switches"][1] == "S2");
  CHECK(document["detectors"].size() == 1);
  CHECK(document["detectors"][0] == "D1");
  CHECK(document["detected_tags"].size() == 1);
  CHECK(document["detected_tags"][0]["detector"] == "D1");
  CHECK(document["detected_tags"][0]["tag_id"] == "04:A1");
}

TEST(protocolFetchesAppliesAndAcknowledgesRuntimeConfiguration) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::ProtocolModule protocol(bus, model);
  train::ReaderModule readers(bus, model);
  JsonCollector output;
  TypeCollector disconnects;

  CHECK(protocol.setup());
  CHECK(readers.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::OutboundDocument),
      &output,
      JsonCollector::receive));
  CHECK(bus.subscribe(
      train::eventMask(EventType::DisconnectRequested),
      &disconnects,
      TypeCollector::receive));

  bus.publish(BackendConnectedEvent());
  JsonDocument request = parseJson(output.values.back());
  CHECK(request["event"] == "config_request");
  CHECK(request["schema"] == 1);
  CHECK(request["device_id"] == "test-device");

  bus.publish(InboundLineEvent(
      "{\"cmd\":\"configure\",\"schema\":1,\"hub\":\"yard\","
      "\"servo_settle_ms\":500,\"switches\":[{\"id\":\"S1\","
      "\"pin\":9,\"straight\":55,\"diverge\":105}],"
      "\"readers\":[{\"id\":\"D1\",\"ss_pin\":4,"
      "\"read_timeout_ms\":25,\"removal_delay_ms\":750}],"
      "\"revision\":\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\"}"));
  CHECK(model.configurationPending);
  CHECK(!model.configurationApplied);
  fake_pn532::queueRead(0, {0x04, 0xA1});
  readers.trigger();
  readers.trigger();

  CHECK(model.configurationApplied);
  CHECK(disconnects.values.empty());
  JsonDocument hello = parseJson(output.values.back());
  CHECK(hello["event"] == "hello");
  CHECK(hello["hub"] == "yard");
  CHECK(hello["revision"] ==
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
  CHECK(hello["switches"][0] == "S1");
  CHECK(hello["detectors"][0] == "D1");
  CHECK(hello["detected_tags"][0]["tag_id"] == "04:A1");
  CHECK(hello["applied"]["switches"][0]["pin"] == 9);
  CHECK(hello["applied"]["readers"][0]["read_timeout_ms"] == 25);
}

TEST(eventLedStopsUsingSpiClockPinWhenReadersAreConfigured) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::EventLedModule led(bus, model, true);
  CHECK(led.setup());
  model.readersUseSpi = true;
  bus.publish(train::ConfigurationChangedEvent());
  const size_t writes = fake_arduino::pinWrites.size();
  bus.publish(WifiConnectedEvent());
  CHECK(fake_arduino::pinWrites.size() == writes);
  CHECK(fake_arduino::pinWrites.back().pin == LED_BUILTIN);
  CHECK(fake_arduino::pinWrites.back().value == HIGH);
}

TEST(protocolDisconnectsWhenConfigurationDoesNotArrive) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::ProtocolModule protocol(bus, model);
  TypeCollector disconnects;
  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::DisconnectRequested),
      &disconnects,
      TypeCollector::receive));

  bus.publish(BackendConnectedEvent());
  fake_arduino::now = 9999;
  protocol.trigger();
  CHECK(disconnects.values.empty());
  fake_arduino::now = 10000;
  protocol.trigger();
  CHECK(disconnects.values ==
        std::vector<EventType>({EventType::DisconnectRequested}));
  CHECK(fake_arduino::serialOutput.empty());
}

TEST(protocolRejectsNumericConfigurationBeforeNarrowing) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::ProtocolModule protocol(bus, model);
  JsonCollector output;
  TypeCollector disconnects;
  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::OutboundDocument),
      &output,
      JsonCollector::receive));
  CHECK(bus.subscribe(
      train::eventMask(EventType::DisconnectRequested),
      &disconnects,
      TypeCollector::receive));

  bus.publish(BackendConnectedEvent());
  bus.publish(InboundLineEvent(
      "{\"cmd\":\"configure\",\"schema\":1,\"hub\":\"yard\","
      "\"servo_settle_ms\":500,\"switches\":[{\"id\":\"S1\","
      "\"pin\":258,\"straight\":55,\"diverge\":105}],"
      "\"readers\":[],"
      "\"revision\":\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\"}"));

  CHECK(!model.configurationPending);
  CHECK(!model.configurationApplied);
  CHECK(disconnects.values ==
        std::vector<EventType>({EventType::DisconnectRequested}));
  JsonDocument rejection = parseJson(output.values.back());
  CHECK(rejection["event"] == "config_rejected");
  CHECK(rejection["reason"] == "invalid_configuration");
}

TEST(protocolRejectsReaderTimeoutBeforeNarrowing) {
  EventBus bus;
  ControllerModel model;
  train::ProtocolModule protocol(bus, model);
  JsonCollector output;
  TypeCollector disconnects;
  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::OutboundDocument),
      &output,
      JsonCollector::receive));
  CHECK(bus.subscribe(
      train::eventMask(EventType::DisconnectRequested),
      &disconnects,
      TypeCollector::receive));

  bus.publish(BackendConnectedEvent());
  bus.publish(InboundLineEvent(
      "{\"cmd\":\"configure\",\"schema\":1,\"hub\":\"yard\","
      "\"servo_settle_ms\":500,\"switches\":[],"
      "\"readers\":[{\"id\":\"D1\",\"ss_pin\":4,"
      "\"read_timeout_ms\":65537,\"removal_delay_ms\":750}],"
      "\"revision\":\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\"}"));

  CHECK(!model.configurationPending);
  CHECK(!model.configurationApplied);
  CHECK(disconnects.values ==
        std::vector<EventType>({EventType::DisconnectRequested}));
  JsonDocument rejection = parseJson(output.values.back());
  CHECK(rejection["event"] == "config_rejected");
  CHECK(rejection["reason"] == "invalid_configuration");
}

TEST(protocolRejectsReaderTimeoutTotalAboveHeartbeatBudget) {
  EventBus bus;
  ControllerModel model;
  train::ProtocolModule protocol(bus, model);
  JsonCollector output;
  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::OutboundDocument),
      &output,
      JsonCollector::receive));

  bus.publish(BackendConnectedEvent());
  bus.publish(InboundLineEvent(
      "{\"cmd\":\"configure\",\"schema\":1,\"hub\":\"yard\","
      "\"servo_settle_ms\":500,\"switches\":[],\"readers\":["
      "{\"id\":\"D1\",\"ss_pin\":4,\"read_timeout_ms\":600,"
      "\"removal_delay_ms\":750},{\"id\":\"D2\",\"ss_pin\":5,"
      "\"read_timeout_ms\":500,\"removal_delay_ms\":750}],"
      "\"revision\":\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\"}"));

  CHECK(!model.configurationApplied);
  CHECK(parseJson(output.values.back())["event"] == "config_rejected");
}

TEST(protocolSuppressesStaleTagEventsDuringConfigurationHandshake) {
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  model.configurationApplied = true;
  train::ProtocolModule protocol(bus, model);
  JsonCollector output;
  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::OutboundDocument),
      &output,
      JsonCollector::receive));

  bus.publish(BackendConnectedEvent());
  const uint8_t uid[] = {0x04, 0xA1};
  bus.publish(TagChangedEvent(0, true, uid, sizeof(uid)));

  CHECK(output.values.size() == 1);
  JsonDocument request = parseJson(output.values[0]);
  CHECK(request["event"] == "config_request");
}

TEST(protocolParsesMovesAndIgnoresMalformedInput) {
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  model.configurationApplied = true;
  train::ProtocolModule protocol(bus, model);
  MoveCollector moves;

  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::MoveSwitchRequested),
      &moves,
      MoveCollector::receive));

  bus.publish(InboundLineEvent("not-json"));
  bus.publish(InboundLineEvent("{}"));
  bus.publish(InboundLineEvent("{\"cmd\":\"move\"}"));
  CHECK(moves.values.empty());

  bus.publish(InboundLineEvent(
      "{\"cmd\":\"move\",\"switch\":\"S1\",\"angle\":180,"
      "\"request_id\":\"request-1\"}"));
  bus.publish(InboundLineEvent(
      "{\"cmd\":\"move\",\"switch\":\"S2\",\"position\":\"diverge\"}"));

  CHECK(moves.values.size() == 2);
  CHECK(moves.values[0].switchId == "S1");
  CHECK(moves.values[0].hasAngle);
  CHECK(moves.values[0].angle == 180);
  CHECK(moves.values[0].requestId == "request-1");
  CHECK(moves.values[1].switchId == "S2");
  CHECK(!moves.values[1].hasAngle);
  CHECK(moves.values[1].position == "diverge");
}

TEST(protocolSerializesPongSwitchAndTagEvents) {
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  model.configurationApplied = true;
  train::ProtocolModule protocol(bus, model);
  JsonCollector output;

  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::OutboundDocument),
      &output,
      JsonCollector::receive));

  bus.publish(InboundLineEvent("{\"cmd\":\"ping\"}"));
  bus.publish(SwitchMovedEvent(1, 110, true, "request-2"));
  const uint8_t uid[] = {0x04, 0x00, 0xAB, 0xCD};
  bus.publish(TagChangedEvent(0, false, uid, sizeof(uid)));

  CHECK(output.values.size() == 3);
  JsonDocument pong = parseJson(output.values[0]);
  JsonDocument moved = parseJson(output.values[1]);
  JsonDocument tag = parseJson(output.values[2]);
  CHECK(pong["event"] == "pong");
  CHECK(pong["hub"] == "test-hub");
  CHECK(moved["event"] == "move_ack");
  CHECK(moved["switch"] == "S2");
  CHECK(moved["angle"] == 110);
  CHECK(moved["ok"] == true);
  CHECK(moved["request_id"] == "request-2");
  CHECK(tag["event"] == "tag_removed");
  CHECK(tag["detector"] == "D1");
  CHECK(tag["tag_id"] == "04:00:AB:CD");
}

TEST(requestIdsAreCopiedIntoFixedEventStorage) {
  const std::string exact(train::REQUEST_ID_SIZE - 1, 'a');
  const std::string oversized(train::REQUEST_ID_SIZE + 10, 'b');

  const MoveSwitchRequestedEvent requested{
      "S1", true, 90, nullptr, exact.c_str()};
  const SwitchMovedEvent moved{0, 90, true, oversized.c_str()};
  const SwitchMovedEvent legacy{0, 90, true};

  CHECK(std::string(requested.requestId) == exact);
  CHECK(
      std::string(moved.requestId) ==
      oversized.substr(0, train::REQUEST_ID_SIZE - 1));
  CHECK(std::string(legacy.requestId).empty());
}

TEST(switchModuleResolvesPositionsAndDetachesAfterSettleTime) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  train::SwitchModule switches(bus, model);
  SwitchCollector moved;

  CHECK(switches.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::SwitchMoved),
      &moved,
      SwitchCollector::receive));

  fake_arduino::now = 100;
  bus.publish(MoveSwitchRequestedEvent(
      "S1", false, 0, "diverge", "request-3"));
  CHECK(moved.values.size() == 1);
  CHECK(moved.values[0].index == 0);
  CHECK(moved.values[0].angle == 105);
  CHECK(moved.values[0].ok);
  CHECK(moved.values[0].requestId == "request-3");
  CHECK(fake_servo::pins[9].attached);
  CHECK(fake_servo::pins[9].angle == 105);

  fake_arduino::now = 599;
  switches.trigger();
  CHECK(fake_servo::pins[9].attached);
  fake_arduino::now = 600;
  switches.trigger();
  CHECK(!fake_servo::pins[9].attached);
  CHECK(!model.switches[0].active);
}

TEST(switchModuleValidatesAnglesAndIgnoresUnknownSwitches) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  train::SwitchModule switches(bus, model);
  SwitchCollector moved;

  CHECK(switches.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::SwitchMoved),
      &moved,
      SwitchCollector::receive));

  bus.publish(MoveSwitchRequestedEvent("missing", true, 90, nullptr));
  CHECK(moved.values.empty());
  bus.publish(MoveSwitchRequestedEvent("S1", true, -1, nullptr));
  bus.publish(MoveSwitchRequestedEvent("S1", true, 181, nullptr));
  bus.publish(MoveSwitchRequestedEvent("S1", false, 0, "sideways"));
  CHECK(moved.values.size() == 3);
  CHECK(!moved.values[0].ok);
  CHECK(!moved.values[1].ok);
  CHECK(!moved.values[2].ok);
  CHECK(fake_servo::pins[9].attachCount == 0);

  bus.publish(MoveSwitchRequestedEvent("S1", true, 0, nullptr));
  bus.publish(MoveSwitchRequestedEvent("S1", true, 180, nullptr));
  CHECK(moved.values[3].ok);
  CHECK(moved.values[4].ok);
  CHECK(fake_servo::pins[9].angle == 180);
}

TEST(readerModuleTracksDetectionReplacementAndRemoval) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  train::ReaderModule readers(bus, model);
  TagCollector changes;

  CHECK(readers.setup());
  model.configurationPending = true;
  bus.publish(train::ConfigurationChangedEvent());
  readers.trigger();
  readers.trigger();
  readers.trigger();
  CHECK(bus.subscribe(
      train::eventMask(EventType::TagChanged),
      &changes,
      TagCollector::receive));
  CHECK(SPI.began);
  CHECK(model.readers[0].ready);
  CHECK(model.readers[1].ready);

  fake_pn532::queueRead(0, {0x04, 0xA1});
  readers.trigger();
  CHECK(changes.values.size() == 1);
  CHECK(changes.values[0].detected);
  CHECK(changes.values[0].uid == std::vector<uint8_t>({0x04, 0xA1}));

  fake_arduino::now = 100;
  fake_pn532::queueRead(0, {0x04, 0xA1});
  fake_pn532::queueMiss(1);
  readers.trigger();
  CHECK(changes.values.size() == 1);

  fake_arduino::now = 200;
  fake_pn532::queueRead(0, {0x04, 0xB2});
  fake_pn532::queueMiss(1);
  readers.trigger();
  CHECK(changes.values.size() == 2);
  CHECK(changes.values[1].detected);
  CHECK(changes.values[1].uid == std::vector<uint8_t>({0x04, 0xB2}));

  fake_arduino::now = 949;
  fake_pn532::queueMiss(0);
  fake_pn532::queueMiss(1);
  readers.trigger();
  CHECK(changes.values.size() == 2);
  fake_arduino::now = 950;
  fake_pn532::queueMiss(0);
  fake_pn532::queueMiss(1);
  readers.trigger();
  CHECK(changes.values.size() == 3);
  CHECK(!changes.values[2].detected);
  CHECK(changes.values[2].uid == std::vector<uint8_t>({0x04, 0xB2}));
  CHECK(!model.readers[0].tagPresent);
  CHECK(fake_arduino::serialOutput.empty());
}

TEST(readerFailureDoesNotDisableOtherReaders) {
  resetFakes();
  fake_pn532::devices[0].firmwareVersion = 0;
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  train::ReaderModule readers(bus, model);
  TagCollector changes;

  CHECK(readers.setup());
  model.configurationPending = true;
  bus.publish(train::ConfigurationChangedEvent());
  readers.trigger();
  readers.trigger();
  readers.trigger();
  CHECK(!model.readers[0].ready);
  CHECK(model.readers[1].ready);
  CHECK(bus.subscribe(
      train::eventMask(EventType::TagChanged),
      &changes,
      TagCollector::receive));

  fake_pn532::queueRead(1, {0x01, 0x02, 0x03});
  readers.trigger();
  CHECK(changes.values.size() == 1);
  CHECK(changes.values[0].index == 1);
  CHECK(changes.values[0].detected);
}

TEST(readerModulePollsEveryOperationalReaderPerTrigger) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  train::ReaderModule readers(bus, model);

  CHECK(readers.setup());
  model.configurationPending = true;
  bus.publish(train::ConfigurationChangedEvent());
  readers.trigger();
  readers.trigger();
  readers.trigger();

  fake_pn532::readTimeouts.clear();
  fake_pn532::queueMiss(0);
  fake_pn532::queueMiss(1);
  readers.trigger();

  CHECK(fake_pn532::readTimeouts == std::vector<uint16_t>({25, 25}));
}

TEST(readerBatchLeavesTimeToProcessHeartbeat) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  configureTestModel(model);
  model.config.readers[0].readTimeoutMs = 500;
  model.config.readers[1].readTimeoutMs = 500;
  train::ReaderModule readers(bus, model);
  train::ProtocolModule protocol(bus, model);
  JsonCollector output;

  CHECK(readers.setup());
  CHECK(protocol.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::OutboundDocument),
      &output,
      JsonCollector::receive));
  model.configurationPending = true;
  bus.publish(train::ConfigurationChangedEvent());
  readers.trigger();
  readers.trigger();
  readers.trigger();
  model.configurationApplied = true;

  fake_pn532::advanceWorstCaseTime = true;
  fake_pn532::queueMiss(0);
  fake_pn532::queueMiss(1);
  readers.trigger();
  CHECK(fake_arduino::now == 2004);

  bus.publish(InboundLineEvent("{\"cmd\":\"ping\"}"));
  CHECK(fake_arduino::now < 3000);
  CHECK(parseJson(output.values.back())["event"] == "pong");
}

TEST(transportConnectsFramesLinesAndSerializesDocuments) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::TransportModule transport(bus, model);
  TypeCollector connections;
  LineCollector lines;

  CHECK(transport.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::BackendConnected) |
          train::eventMask(EventType::BackendDisconnected),
      &connections,
      TypeCollector::receive));
  CHECK(bus.subscribe(
      train::eventMask(EventType::InboundLine),
      &lines,
      LineCollector::receive));

  model.wifiConnected = true;
  bus.publish(WifiConnectedEvent());
  transport.trigger();
  CHECK(model.backendConnected);
  CHECK(fake_wifi::client.connectCount == 1);
  CHECK(fake_wifi::client.host == "backend.test");
  CHECK(fake_wifi::client.port == 9000);
  CHECK(connections.values == std::vector<EventType>({EventType::BackendConnected}));

  fake_wifi::receive("first\n\nsecond\npartial");
  transport.trigger();
  CHECK(lines.values == std::vector<std::string>({"first", "second"}));

  JsonDocument document;
  document["event"] = "test";
  bus.publish(OutboundDocumentEvent(document));
  CHECK(fake_wifi::client.output == "{\"event\":\"test\"}\r\n");

  bus.publish(WifiDisconnectedEvent());
  CHECK(!model.backendConnected);
  CHECK(fake_wifi::client.stopCount == 1);
  CHECK(connections.values.back() == EventType::BackendDisconnected);
}

TEST(transportThrottlesReconnectsAndDiscardsLongLines) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::TransportModule transport(bus, model);
  LineCollector lines;

  CHECK(transport.setup());
  CHECK(bus.subscribe(
      train::eventMask(EventType::InboundLine),
      &lines,
      LineCollector::receive));
  model.wifiConnected = true;
  fake_wifi::client.connectSucceeds = false;

  transport.trigger();
  fake_arduino::now = 1999;
  transport.trigger();
  CHECK(fake_wifi::client.connectCount == 0);
  fake_arduino::now = 2000;
  transport.trigger();
  CHECK(fake_wifi::client.connectCount == 1);
  fake_arduino::now = 3999;
  transport.trigger();
  CHECK(fake_wifi::client.connectCount == 1);
  fake_arduino::now = 4000;
  transport.trigger();
  CHECK(fake_wifi::client.connectCount == 2);

  const std::string largestValidLine(MAX_CONFIG_FRAME_BYTES - 1, 'x');
  fake_wifi::receive(largestValidLine + "\n");
  transport.trigger();
  CHECK(lines.values == std::vector<std::string>({largestValidLine}));

  fake_wifi::receive(std::string(2000, 'x'));
  transport.trigger();
  CHECK(lines.values.size() == 1);
  fake_wifi::receive(std::string(48, 'x') + "\nvalid\n");
  transport.trigger();
  CHECK(lines.values.size() == 2);
  CHECK(lines.values[1] == "valid");
}

TEST(wifiModulePublishesTransitionsAndRetries) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::WifiModule wifi(bus, model);
  TypeCollector changes;

  CHECK(bus.subscribe(
      train::eventMask(EventType::WifiConnected) |
          train::eventMask(EventType::WifiDisconnected),
      &changes,
      TypeCollector::receive));
  CHECK(wifi.setup());
  CHECK(fake_wifi::wifi.beginCount == 1);
  CHECK(fake_wifi::wifi.ssid == "test-wifi");

  fake_arduino::now = 1999;
  wifi.trigger();
  CHECK(fake_wifi::wifi.beginCount == 1);
  fake_arduino::now = 2000;
  wifi.trigger();
  CHECK(fake_wifi::wifi.beginCount == 2);

  fake_wifi::wifi.status = WL_CONNECTED;
  wifi.trigger();
  CHECK(model.wifiConnected);
  CHECK(changes.values.back() == EventType::WifiConnected);
  fake_wifi::wifi.status = WL_DISCONNECTED;
  wifi.trigger();
  CHECK(!model.wifiConnected);
  CHECK(changes.values.back() == EventType::WifiDisconnected);
}

TEST(eventLoggerPrintsEveryEventWhenEnabled) {
  resetFakes();
  EventBus bus;
  train::EventLoggerModule logger(bus, true);

  CHECK(logger.setup());
  bus.publish(WifiConnectedEvent());
  bus.publish(WifiDisconnectedEvent());
  bus.publish(BackendConnectedEvent());
  bus.publish(BackendDisconnectedEvent());
  bus.publish(InboundLineEvent("line"));
  JsonDocument document;
  bus.publish(OutboundDocumentEvent(document));
  bus.publish(MoveSwitchRequestedEvent("S1", true, 90, nullptr));
  bus.publish(SwitchMovedEvent(0, 90, true));
  const uint8_t uid[] = {0x04};
  bus.publish(TagChangedEvent(0, true, uid, sizeof(uid)));

  CHECK(fake_arduino::serialOutput ==
        "event: wifi_connected\n"
        "event: wifi_disconnected\n"
        "event: backend_connected\n"
        "event: backend_disconnected\n"
        "event: inbound_line\n"
        "event: outbound_document\n"
        "event: move_switch_requested\n"
        "event: switch_moved\n"
        "event: tag_changed\n");
}

TEST(eventLoggerDoesNothingWhenDisabled) {
  resetFakes();
  EventBus bus;
  train::EventLoggerModule logger(bus, false);

  CHECK(logger.setup());
  bus.publish(WifiConnectedEvent());

  CHECK(fake_arduino::serialOutput.empty());
}

TEST(eventLedBlipsOnEveryEvent) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::EventLedModule led(bus, model, true);

  CHECK(led.setup());
  CHECK(fake_arduino::pinModes.size() == 1);
  CHECK(fake_arduino::pinModes[0] == std::make_pair(LED_BUILTIN, OUTPUT));
  CHECK(fake_arduino::pinWrites.back().value == HIGH);

  fake_arduino::now = 100;
  bus.publish(WifiConnectedEvent());
  CHECK(fake_arduino::pinWrites.back().value == LOW);

  fake_arduino::now = 149;
  led.trigger();
  CHECK(fake_arduino::pinWrites.back().value == LOW);
  fake_arduino::now = 150;
  led.trigger();
  CHECK(fake_arduino::pinWrites.back().value == HIGH);

  fake_arduino::now = 200;
  bus.publish(BackendConnectedEvent());
  CHECK(fake_arduino::pinWrites.back().value == LOW);
  fake_arduino::now = 225;
  const uint8_t secondUid[] = {0x05};
  bus.publish(TagChangedEvent(0, true, secondUid, sizeof(secondUid)));
  fake_arduino::now = 274;
  led.trigger();
  CHECK(fake_arduino::pinWrites.back().value == LOW);
  fake_arduino::now = 275;
  led.trigger();
  CHECK(fake_arduino::pinWrites.back().value == HIGH);
}

TEST(eventLedDoesNothingWhenLoggingIsDisabled) {
  resetFakes();
  EventBus bus;
  ControllerModel model;
  train::EventLedModule led(bus, model, false);

  CHECK(led.setup());
  bus.publish(WifiConnectedEvent());
  led.trigger();

  CHECK(fake_arduino::pinModes.empty());
  CHECK(fake_arduino::pinWrites.empty());
}

}  // namespace

int main() {
  int failures = 0;
  for (const TestCase& test : tests()) {
    try {
      test.run();
      std::cout << "PASS " << test.name << '\n';
    } catch (const std::exception& error) {
      ++failures;
      std::cerr << "FAIL " << test.name << ": " << error.what() << '\n';
    }
  }
  std::cout << (tests().size() - failures) << "/" << tests().size()
            << " firmware tests passed\n";
  return failures == 0 ? 0 : 1;
}
