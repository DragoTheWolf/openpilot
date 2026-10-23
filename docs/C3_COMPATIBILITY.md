# Original comma 3 compatibility

This fork restores source support removed upstream for the original comma 3
(tici / internal DOS panda / STM32F413 / AR0231 cameras). The comma 3X and comma
four continue to use the H7 controller target.

## Installer bootstrap

The requested OS remains AGNOS 20.1. The launcher selects the modern updater
when `weston-ready` is active; otherwise it uses comma's original Qt/Magic
updater. The AGNOS flasher defers annotations so it can import under the older
installed Python before the OS upgrade. Partition checks, hashes, and the
existing A/B update and reboot flow remain in use.

The legacy executable is unmodified from official comma release v0.9.7,
commit `50dd024081496cc5f036a99c8f62d2887112dbb7`:

- Source: `selfdrive/ui/qt/setup/updater.cc` in that commit.
- LFS artifact: `system/hardware/tici/updater` in that commit.
- SHA-256: `f74ea28934c6b9477a98dc6a38e6bfcd53e94e6af31dba5b6d11bc5310f7d995`.
- Size: 8,135,168 bytes; downloaded and verified from comma's official LFS store.

No dragonpilot or IQ runtime or executable is used. Dragonpilot's installer
was a reference for the legacy-display selection and original-device gaps.

## Runtime and firmware

- AR0231 source and register tables come from comma openpilot commit
  `a254a05df057e5ad8ea3650de553eef4d6804852`, before their removal. Modern
  sensors retain their probe order; AR0231 is an additional fallback.
- F4 hardware source comes from comma panda commit
  `3dc21386239e3073a623156b75901aa302340d6c`, before its removal. It is adapted
  to the current board, health, debug, fan, and safety interfaces.
- Current opendbc safety code, including this fork's scoped PQ CC-only AOL
  behavior, is compiled for both MCU targets. No historical safety code is
  substituted. F4 uses classical CAN and reports CAN-FD disabled.
- Firmware and DFU selection use the detected MCU. Unknown board types fail
  instead of assuming an F4 or flashing an H7 image onto it.
- The original USB transport is adapted to the current host interface; SPI
  remains available. USB receive waits are bounded so a quiet bus cannot
  block heartbeat processing.
- F4 queues fit its RAM with a linker assertion protecting the stack and
  reset cookies. H7 queue sizes and its stop-mode implementation are retained.
- Startup mounts an existing original-C3 NVMe partition if present and not
  already mounted. It does not format storage.
- Original C3 single-speaker routing and equalization are restored from the
  same official openpilot source, using the current I2C implementation.

## Validation limits

Desktop/native compilation and tests do not confirm the physical C3 update
prompt, AGNOS 20.1 boot, all three cameras, USB controller recovery, NVMe,
or on-road operation. No original C3 logs or reachable SSH connection were
available during implementation. Treat this as a hardware test candidate;
the reported logo hang has not yet been reproduced or confirmed fixed on
the device. First startup builds the controller firmware and model.
