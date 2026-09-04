# PN532 reader test firmware

`TestController` is a standalone Arduino firmware for validating a PN532 and
reading the tag attached to a train. It does not initialize Wi-Fi, switches,
detectors, or motors. Firmware versions are recorded in
`firmware_config.h` and printed at boot.

## Wiring

| PN532 | Arduino UNO R4 WiFi |
| --- | --- |
| VCC | 5V |
| GND | GND |
| SCK | D13 |
| MOSI | D11 |
| MISO | D12 |
| SS | D4 |

Set the PN532 board to **SPI mode before powering it on**. Check the markings
or manual for the specific PN532 module. Also confirm that the module accepts
5 V power; a bare 3.3 V PN532 board must not be powered from 5 V.

## Dependency

Install the `Adafruit PN532` library (and its `Adafruit BusIO` dependency) in
the Arduino IDE Library Manager, or with Arduino CLI:

```sh
arduino-cli lib install "Adafruit PN532"
```

## Compile, upload, and monitor

From the repository root, explicitly select this sketch:

```sh
./ard --sketch TestController compile
./ard --sketch TestController go
./ard --baudrate 115200 monitor
```

The serial output reports each initialization stage, chip and firmware
identification, reader readiness, tag UID, tag removal, re-arming, and a
five-second heartbeat while no tag is present.
