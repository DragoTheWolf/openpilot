## Neural networks in openpilot
To view the architecture of the ONNX networks, you can use [netron](https://netron.app/)

## Testing fork default: Rebellious Hope

`driving_supercombo.onnx` is comma's original, unmodified Rebellious Hope artifact from
[commit 93f5aa469a72b7621aef7da7901c100e0113e4d9](https://github.com/commaai/openpilot/commit/93f5aa469a72b7621aef7da7901c100e0113e4d9).
It is fetched from comma's configured Git LFS endpoint, not IQ.Pilot or a third-party model mirror.

- SHA-256: `433f85f956837606ad1f1cbee4aa7e2158ad23c768dea914b20436c97232741b`
- Size: 96,599,486 bytes.
- Checkpoint: `5c5d862b-d4dd-4087-aa8b-232ff9ac943f/100/d0c60276-564d-4b97-a59c-f1ab853d8c26/400`.
- Lateral smoothing: 0.1 seconds, matching that original commit.

The ONNX has legacy image/history inputs. `compile_rebellious_hope.py` verifies its hash and wraps it for the current explicit-state runtime, preserving comma's original 20 Hz queues, 5 Hz image/feature sampling, and max-pooled desire pulses. The original weights and ONNX graph remain unchanged. The adapter compiler is used only for the default driving model; driver monitoring and the optional Chestnut model are unchanged.

Comma later [reverted this model](https://github.com/commaai/openpilot/commit/b361e952c9da023412c6744278cc9421b2c90b8c); its revert description does not specify a reason. This is a user-requested experimental default, not the current upstream recommendation. CPU compilation/serialization, temporal queue tests, and production `ModelState` warmup/inference at both camera resolutions pass; QCOM device timing and driving behavior remain unverified.
