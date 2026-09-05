# Firmware tests

Run the native behavior tests and compile the production sketch for the UNO R4:

```sh
python3 firmware/tests/run.py
```

The native suite compiles the production module sources against narrow fakes for
the clock, status LED, Wi-Fi client, servos, SPI bus, and PN532 readers. The
generated configuration is a test fixture and does not read or modify `data/`.

Use `--host-only` while iterating or `--compile-only` to run just the board
compilation smoke test. Physical wiring and radio behavior still require a real
controller and are intentionally outside this suite.
