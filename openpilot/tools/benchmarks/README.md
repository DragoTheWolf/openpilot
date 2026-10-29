# Selectable bench workloads

The `bench` branch starts from `testing` 2d0af82 and keeps experiments separate from
the driving branch. Run the device on its bench power supply, with cooling and
the normal offroad runtime available. The runner never enables driving,
changes Params, sends CAN commands, or changes panda safety mode. It refuses
to start on-road on a comma device and checks the offroad state while running.

Select only the hardware you want. Nothing is selected automatically:

```sh
# Preview the configuration; no workloads or result files are created.
python openpilot/tools/benchmarks/bench.py --components cpu memory --dry-run

# Two CPU workers at a 50% duty cycle, plus 256 MiB of repeatedly written RAM.
# This does not start camerad or a storage workload.
python openpilot/tools/benchmarks/bench.py --components cpu memory --duration 120

# CPU only, one worker at full load.
python openpilot/tools/benchmarks/bench.py --components cpu --cpu-workers 1 --cpu-load 100

# Memory only; keep the rest of the test selection unchanged.
python openpilot/tools/benchmarks/bench.py --components memory --memory-mib 512

# Camera workload, optionally combined with other selections.
python openpilot/tools/benchmarks/bench.py --components cameras --duration 60

# Read-only storage capacity, mount and available SMART information.
python openpilot/tools/benchmarks/bench.py --components storage-health --storage-dir /data/media/0

# Storage speed plus integrity, using its own temporary file on this filesystem.
python openpilot/tools/benchmarks/bench.py --components storage --storage-dir /data/media/0 --storage-file-mib 128

# Combined CPU, RAM and storage stress; cameras remain unselected.
python openpilot/tools/benchmarks/bench.py --components cpu memory storage --duration 120
```

The device Python environment is required for the camera adapter; CPU, memory
and storage workloads use only the Python standard library on Linux. Run from
an SSH login with the normal openpilot environment. `--openpilot-dir` can point
the camera adapter at another native build. The camera selection refuses to
start if camerad already runs, owns only the camerad process it launches, and
checks all three streams for valid advancing frames. It does not start modeld
or controlsd. CPU/memory selections never call the camera adapter. Camera
bench operation still needs a physical bench test; the device was off during
development of this runner.

Runs write a manifest, timestamped samples and summary under `/data/benchmarks`
(or `./benchmark-results` on desktop Linux). Samples include system CPU usage,
available memory, thermal sensors, hash work counts, RAM bytes written, camera
frame IDs when selected, and storage pass results when selected. Compare
identical selections, load, duration, cooling, power supply and software versions.
CPU percentages describe the whole machine, not a single core. Memory stress
also consumes CPU and bandwidth; these are selectable workloads, not perfectly
isolated hardware measurements. A storage-health-only invocation records the
manifest and health report without starting a timed workload or sample stream.

Storage tests repeatedly write only a bounded temporary file in the selected
directory, flush it with fsync, reread it and compare SHA-256. They preserve
existing files and remove their own temporary directory on normal cleanup.
They intentionally write to flash, unlike `storage-health`. Read speeds are
explicitly labelled cached: the runner does not drop system caches. This is
not a full-device bad-block scan or a guarantee against future failure. SMART
may be unsupported or inaccessible; that is reported as unavailable, not healthy.
Use `--storage-dir /data` to test internal storage separately from mounted NVMe
at `/data/media/0`; inspect the reported mount to confirm the actual device.

Default thermal stop is 80 C (configurable 50–85 C). The runner checks memory
headroom and reserves disk space for storage tests. It stops if the device
goes on-road, a selected workload fails, thermal monitoring disappears on the
device, or temperature/memory limits are reached. Ctrl+C stops and cleans up
only processes it created. Thermal stops have up to one sample interval of
latency, plus any in-flight kernel I/O. Abrupt power loss may leave a temporary
test directory; the prefix is `openpilot-bench-` in the selected storage directory.

Next candidates: GPU/model inference, encoder throughput, camera frame latency,
recorded-drive replay with no vehicle actuation, USB/panda communication soak,
and reports comparing runs. No driving-performance claim follows from a bench
stress result.
