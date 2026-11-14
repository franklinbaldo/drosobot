# DrosoBot Firmware Lab (ESP32-C3)

This directory is a **read-only research track**, not a buildable firmware image. The existing Xiaozhi firmware remains in place. `reference-board.toml` transcribes the official ESP-Hi pin configuration and marks every unknown as unverified; nothing was measured on the physical unit.

Next steps: capture device/firmware inventory with a safe method, document reversible backup and recovery, obtain a separate test board, and only then compare [esp-rs/esp-idf](https://github.com/esp-rs/esp-idf) versus [esp-rs/esp-hal](https://github.com/esp-rs/esp-hal). No flashing/servo changes without explicit authorization.

Be aware: the ESP-Hi documentation notes that servo control may occupy the USB Type-C interface and interfere with flashing/debugging while the robot body is attached. The recovery procedure must be demonstrated before any experiment.
