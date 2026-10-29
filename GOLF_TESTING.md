# Golf PQ factory cruise testing branch

This branch targets a 2014 North American automatic Volkswagen Golf PQ using the Passat NMS compatibility selection. Factory cruise retains speed control; openpilot provides steering. CC-only detection requires engine cruise traffic and no detected radar ACC traffic. The recorded gateway layout uses powertrain bus 1 and steering TX bus 0.

The Passat NMS selection is a compatibility alias, not a verified Golf-specific tune. Existing minimum steering speed and torque protections remain. This port requires locally built panda firmware with `ALLOW_DEBUG` (`RELEASE` unset); stock release firmware rejects the PQ safety mode. No IQ.Pilot binaries, UI, or radarless branches are included.

The opendbc submodule is pinned to the matching modified commit in `DragoTheWolf/opendbc`. Clone submodules recursively; keep the pinned revision when building.

## Manual vehicle selection

In **Settings → Toggles → Manual Fingerprint**, choose **Passat NMS** for this Golf PQ, or **Automatic** to use normal detection. The setting is available on both the comma 3/3X and comma 4 UI layouts, can be changed only offroad, and persists across reboots. Reboot after changing it. The default remains Passat NMS for this dedicated Golf fork.

Manual selection skips VIN/firmware identification queries and still collects live CAN to determine topology and validate the scoped CC-only configuration. It does not bypass missing CAN or enable the port on an empty fingerprint. Selecting a mode clears the cached vehicle parameters. Invalid saved model names fall back to automatic detection. The former hardcoded launch override has been replaced by this setting.

## Factory cruise engagement

The engine state correctly reports this car's cruise as non-adaptive. The generic `wrongCruiseMode` event previously interpreted that as an unsupported mode and displayed "Adaptive Cruise Disabled". The engagement event check now permits non-adaptive cruise specifically for Volkswagen `PQ_CC_ONLY` with factory longitudinal control (`pcmCruise`, without openpilot longitudinal). Other configurations retain the normal block. Engine cruise engagement, cancellation, cruise faults, and other engagement protections are unchanged.

## Flashed PQ EPS

For an EPS already patched to support low-speed steering, enable **Settings → Toggles → Flashed PQ EPS** while offroad, then reboot. This persistent setting defaults off. It applies the IQ release's `VwPqEpsPatched` behavior (`minSteerSpeed = 0`) specifically to the detected NMS/Golf PQ CC-only configuration. With it off, the existing 50 km/h (31 mph) minimum remains.

This changes the steering-speed parameter and resulting low-speed alert; it does not flash the EPS. Minimum engagement speed, normal standstill behavior, torque/rate limits, and fault handling remain unchanged. Independent engagement is separately controlled by the optional AOL setting below.

The flashed-EPS update passes **204 tests and 106 subtests**, with 81 skips, across setting persistence/scope, existing interface propagation, low-speed alerts, engagement/manual selection, Params, Volkswagen vehicle and PQ safety tests. Ruff, incremental Linux build, and both UI layout/render/offroad-edit checks pass. Physical low-speed steering remains to be validated on the user's flashed rack.

## AOL / MADS for factory CC

Enable **Settings → Toggles → AOL (CC Only)** offroad and reboot. It defaults off and applies only to this detected NMS/Golf PQ CC-only configuration. The matching panda debug firmware must be rebuilt from the pinned modified opendbc source; startup's firmware signature check handles a stale installed panda image. This mode adds no acceleration commands or automatic SET/RESUME messages.

- Flipping cruise main off then on requests steering engagement, subject to normal checks. A switch already on at startup does not automatically engage. Engaging factory cruise also requests steering engagement.
- After a cancellation, a deliberate SET/RES button press and release requests engagement again. Those physical buttons also retain their normal factory-cruise function.
- Braking cancels factory speed control normally and retains already-engaged AOL steering. A held brake cannot start a new steering engagement. Releasing the brake does not start a disabled steering session.
- Cancel, main off, or an engine cruise fault disengages steering. Clearing a fault does not automatically re-engage it.
- Stopped changes into Park, Neutral or Reverse disengage with the normal cue instead of an urgent takeover alarm. Non-driving gears still block engagement; returning to Drive requires a fresh switch cycle or SET/RES action. Moving gear warnings retain their normal urgency.
- On C3/C3X, active AOL steering without factory speed control has a light-blue bottom strip. Factory cruise plus steering has a full dark-blue border. Inactive steering has no active AOL strip; overrides and alerts retain their normal presentation.
- Factory cruise alone controls speed. Disengaging steering does not automatically send a factory-cruise cancel. The brake-retention exception is restricted to the explicitly selected PQ CC-only AOL safety mode; stock PQ and other safety modes retain their normal brake disengagement. Door, seatbelt, gear, driver-monitoring, steering-fault, torque/rate, receive-validity, relay, and heartbeat protections remain. Normal Park/reverse and standstill policies are retained; this is not a parked steering override.

PQ active steering already uses **HCA7**, with HCA3 for inactive/zero-torque output. A controller-output test verifies this; no HCA5 switch or torque-limit relaxation was needed.

The October 29 switch/display update passes 379 focused host/UI/Volkswagen tests
(131 skipped, 20 subtests), 3,030 full native safety tests (1,395 skipped, 9,736
subtests), MISRA analysis, Python lint and F4/H7 firmware builds. The C3 UI
border code was rendered offline. Physical testing of these latest switch,
gear-alert and display changes remains pending; the device was powered off.

## Default model

The default driving model is now comma's original **Rebellious Hope**, taken only from comma commit `93f5aa4` and its official LFS artifact. See `openpilot/selfdrive/modeld/models/README.md` for the hash, historical upstream revert, and the compatibility wrapper required by the newer runtime. IQ's model/runtime is not used.

Final brake-handoff validation: **3,095 passed, 1,395 skipped, 9,835 subtests passed** across the complete native safety suite and AOL/model/vehicle regressions. MISRA/mutation checks, incremental Linux build, and ARM panda debug build pass. The original Rebellious Hope model compilation/serialization, production model runtime warmup/inference at 1928×1208 and 1344×760, and temporal sampling tests pass. Physical AOL operation, QCOM model timing, and driving behavior remain unverified. Original C3 legacy-updater/F4/AR0231 support is separate work and is not included in this update.

Native tests using decoded engine CAN cover engagement requests, cancellation/faults, other engagement protections, and preservation of the mode block outside the scoped configuration. Combined engagement/manual-selection/Volkswagen/PQ safety suites: **182 passed, 81 skipped, 106 subtests passed**; lint and incremental Linux build passed. The user reports onroad entry and calibration on the prior version, with engagement blocked by this alert. The fix still needs confirmation on the physical device.

## Completed offline validation

- Ubuntu 24.04 / WSL2: full x86_64 desktop openpilot default SCons build passed.
- Panda H7 debug firmware and bootstub compiled from source.
- Native Volkswagen vehicle/PQ safety: 162 tests and 106 subtests passed, 81 skipped.
- Native MQB/default-safety regressions: 86 tests and 4 subtests passed, 45 skipped.
- Native safety builds used upstream UBSan and warnings-as-errors. Debug PQ selection succeeds; release selection is rejected.
- Manual selection update: full incremental Linux build passed; persistence, manual identification, Params, Volkswagen vehicle and PQ safety suites report **181 passed, 81 skipped, 106 subtests passed**. Both UI layouts rendered under a virtual display, with offroad editing and onroad blocking checked.
- Approximately 34 minutes of recorded Golf CAN: all 204,287 vehicle updates after warmup CAN-valid; 143,212 commands generated by this controller with zero safety rejections. Recorded IQ torque requests were test inputs; this did not replay the upstream planner. Historical IQ steering commands themselves had safety rejections.

## Hardware validation outstanding

No flashing, hardware boot tests, or in-car validation have been performed for this fork. Verify harness identity, NMS alias behavior, firmware communication, steering behavior, and HCA timeout recovery. Comma 3, 3X, and 4 compatibility is unverified. The desktop build is not a device OS image or proof of road readiness.
