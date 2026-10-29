#!/usr/bin/env python3
"""Selectable Linux bench workloads. Never enables driving or changes parameters."""
import argparse
import ctypes
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import time

MIB = 1024 * 1024
CAMERA_SERVICES = ('narrowRoadCameraState', 'wideRoadCameraState', 'cabinCameraState')


def memory_info():
  values = {}
  for line in Path('/proc/meminfo').read_text().splitlines():
    key, value, *_ = line.split()
    values[key.rstrip(':')] = int(value) * 1024
  return {'total': values['MemTotal'], 'available': values['MemAvailable']}


def cpu_times():
  values = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
  return sum(values), values[3] + values[4]


def temperatures():
  result = {}
  for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
    try:
      value = float((zone / 'temp').read_text()) / 1000
      if -40 <= value <= 150:
        result[f'{zone.name}:{(zone / "type").read_text().strip()}'] = value
    except (OSError, ValueError):
      continue
  return result


def require_offroad(hardware=Path('/AGNOS'), params=Path('/data/params/d')):
  if hardware.exists():
    if not (params / 'IsOffroad').exists() or (params / 'IsOffroad').read_text().strip() != '1':
      raise RuntimeError('Bench workloads require the device to be offroad.')


def validate_resources(components, requested_mib, info):
  if 'memory' in components:
    reserve = max(512 * MIB, int(info['total'] * 0.15))
    if requested_mib * MIB > info['available'] - reserve:
      raise ValueError('Requested memory would leave less than 512 MiB or 15% of RAM free; lower --memory-mib.')


def cpu_worker(stop, load, counter):
  block = b'openpilot bench CPU' * 256
  while not stop.is_set():
    start = time.monotonic()
    while time.monotonic() - start < 0.1 * load and not stop.is_set():
      hashlib.sha256(block).digest()
      counter.value += 1
    stop.wait(max(0, 0.1 - (time.monotonic() - start)))


def memory_worker(stop, size_mib, counter):
  data = bytearray(size_mib * MIB)
  address = ctypes.addressof(ctypes.c_char.from_buffer(data))
  value = 0
  while not stop.is_set():
    ctypes.memset(address, value, len(data))
    counter.value += len(data)
    value ^= 0xFF


def storage_health(directory):
  directory = directory.resolve(strict=True)
  usage = shutil.disk_usage(directory)
  report = {'directory': str(directory), 'total_mib': usage.total / MIB, 'free_mib': usage.free / MIB,
            'free_percent': 100 * usage.free / usage.total, 'smart': {'status': 'unavailable'}}
  if shutil.which('findmnt'):
    result = subprocess.run(['findmnt', '-J', '-T', str(directory), '-o', 'SOURCE,TARGET,FSTYPE,OPTIONS'],
                            capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
      mount = json.loads(result.stdout)['filesystems'][0]
      report['mount'] = mount
      source = mount['source'].split('[')[0]
      if source.startswith('/dev/') and shutil.which('smartctl'):
        smart = subprocess.run(['smartctl', '-j', '-H', '-A', source], capture_output=True, text=True, timeout=15)
        try:
          data = json.loads(smart.stdout)
          passed = data.get('smart_status', {}).get('passed')
          critical = data.get('nvme_smart_health_information_log', {}).get('critical_warning', 0)
          if passed is False or (isinstance(critical, int) and critical > 0):
            status = 'failed'
          elif smart.returncode & 7:
            status = 'unavailable'
          else:
            status = 'attention' if smart.returncode else 'reported'
          report['smart'] = {'status': status, 'exit_code': smart.returncode, 'data': data}
        except ValueError:
          report['smart'] = {'status': 'unavailable', 'detail': (smart.stderr or smart.stdout)[:2000]}
  return report


def storage_worker(stop, directory, size_mib, results):
  # The only file this worker writes lives inside its own new temporary directory.
  with tempfile.TemporaryDirectory(prefix='openpilot-bench-', dir=directory) as temporary:
    test_file = Path(temporary).resolve() / 'integrity.bin'
    assert test_file.is_relative_to(Path(directory).resolve())
    block = os.urandom(MIB)
    while not stop.is_set():
      reserve = max(1024 * MIB, int(shutil.disk_usage(directory).total * 0.05))
      if shutil.disk_usage(directory).free < size_mib * MIB + reserve:
        raise RuntimeError('Insufficient free space for the storage test and reserve.')
      expected = hashlib.sha256()
      start = time.monotonic()
      with test_file.open('wb') as file:
        for _ in range(size_mib):
          if stop.is_set():
            return
          file.write(block)
          expected.update(block)
        file.flush()
        flush_start = time.monotonic()
        os.fsync(file.fileno())
        flush_ms = (time.monotonic() - flush_start) * 1000
      write_seconds = time.monotonic() - start
      actual = hashlib.sha256()
      start = time.monotonic()
      with test_file.open('rb') as file:
        while data := file.read(MIB):
          if stop.is_set():
            return
          actual.update(data)
      read_seconds = time.monotonic() - start
      if actual.digest() != expected.digest():
        raise RuntimeError('Storage data integrity verification failed.')
      result = {'write_mib_s': size_mib / write_seconds, 'cached_read_mib_s': size_mib / read_seconds,
                'fsync_ms': flush_ms, 'integrity_ok': True, 'file_mib': size_mib}
      try:
        results.put(result, timeout=0.1)
      except queue.Full:
        pass
      stop.wait(0.1)


class Workloads:
  def __init__(self, args, output):
    self.args = args
    self.output = output
    self.stop = mp.Event()
    self.workers = []
    self.cpu_counters = []
    self.memory_counter = mp.Value('Q', 0)
    self.camera = None
    self.camera_log = None
    self.messages = None
    self.camera_first = {}
    self.camera_last = {}
    self.storage_results = mp.Queue(maxsize=16)
    self.storage_last = None
    self.storage_passes = 0

  def start(self):
    if 'cameras' in self.args.components:
      self.start_cameras()
    if 'cpu' in self.args.components:
      for _ in range(self.args.cpu_workers):
        counter = mp.Value('Q', 0)
        self.cpu_counters.append(counter)
        self.workers.append(mp.Process(target=cpu_worker, args=(self.stop, self.args.cpu_load / 100, counter)))
    if 'memory' in self.args.components:
      self.workers.append(mp.Process(target=memory_worker, args=(self.stop, self.args.memory_mib, self.memory_counter)))
    if 'storage' in self.args.components:
      self.workers.append(mp.Process(target=storage_worker, args=(self.stop, str(self.args.storage_dir.resolve()),
                                                               self.args.storage_file_mib, self.storage_results)))
    for worker in self.workers:
      worker.start()

  def start_cameras(self):
    if not Path('/AGNOS').exists():
      raise RuntimeError('The camera workload requires a comma device and its native openpilot runtime.')
    if subprocess.run(['pgrep', '-x', 'camerad'], stdout=subprocess.DEVNULL).returncode == 0:
      raise RuntimeError('camerad is already running. Close the camera preview before starting this workload.')
    root = self.args.openpilot_dir.resolve()
    binary = root / 'openpilot/system/camerad/camerad'
    if not binary.is_file():
      raise RuntimeError(f'Build camerad first: missing {binary}')
    sys.path.insert(0, str(root))
    from openpilot.cereal import messaging
    self.messages = messaging.SubMaster(list(CAMERA_SERVICES))
    self.camera_log = (self.output / 'camerad.log').open('w')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(root) + os.pathsep + env.get('PYTHONPATH', '')
    self.camera = subprocess.Popen([str(binary)], cwd=binary.parent, env=env,
                                   stdout=self.camera_log, stderr=subprocess.STDOUT, start_new_session=True)

  def sample(self):
    while True:
      try:
        self.storage_last = self.storage_results.get_nowait()
        self.storage_passes += 1
      except queue.Empty:
        break
    for worker in self.workers:
      if worker.exitcode is not None:
        raise RuntimeError(f'Workload exited unexpectedly: PID {worker.pid}, exit {worker.exitcode}')
    if self.camera is not None and self.camera.poll() is not None:
      raise RuntimeError(f'camerad exited with {self.camera.returncode}; see camerad.log')
    if self.messages is not None:
      self.messages.update(0)
      for name in CAMERA_SERVICES:
        if self.messages.updated[name] and self.messages.valid[name]:
          frame = self.messages[name].frameId
          self.camera_first.setdefault(name, frame)
          self.camera_last[name] = frame
    return {'cpu_hashes': sum(v.value for v in self.cpu_counters), 'memory_bytes_written': self.memory_counter.value,
            'camera_frame_ids': self.camera_last.copy(), 'storage_passes': self.storage_passes, 'storage': self.storage_last}

  def close(self):
    self.stop.set()
    for worker in self.workers:
      if worker.pid is None:
        continue
      worker.join(3)
      if worker.is_alive():
        worker.terminate()
        worker.join(3)
      if worker.is_alive():
        worker.kill()
        worker.join(3)
    if self.camera is not None and self.camera.poll() is None:
      self.camera.send_signal(signal.SIGINT)
      try:
        self.camera.wait(5)
      except subprocess.TimeoutExpired:
        self.camera.kill()
        self.camera.wait()
    if self.camera_log is not None:
      self.camera_log.close()
    self.storage_results.close()


def parse_args(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--components', nargs='+', choices=['cpu', 'memory', 'cameras', 'storage', 'storage-health'], required=True)
  parser.add_argument('--duration', type=float, default=60, help='Run time in seconds, 1 to 86400.')
  parser.add_argument('--cpu-workers', type=int, default=min(2, os.cpu_count() or 1))
  parser.add_argument('--cpu-load', type=float, default=50, help='Target duty cycle per CPU worker, 1 to 100 percent.')
  parser.add_argument('--memory-mib', type=int, default=256)
  parser.add_argument('--storage-dir', type=Path, default=Path('/data/media/0') if Path('/AGNOS').exists() else Path.cwd())
  parser.add_argument('--storage-file-mib', type=int, default=128, help='Temporary test file size, 1 to 4096 MiB.')
  parser.add_argument('--thermal-limit-c', type=float, default=80, help='Stop at this hottest reported sensor temperature (50 to 85 C).')
  parser.add_argument('--sample-interval', type=float, default=1)
  parser.add_argument('--output', type=Path, default=Path('/data/benchmarks') if Path('/AGNOS').exists() else Path('benchmark-results'))
  parser.add_argument('--openpilot-dir', type=Path, default=Path(__file__).resolve().parents[3])
  parser.add_argument('--dry-run', action='store_true', help='Print the selection without starting workloads or writing files.')
  args = parser.parse_args(argv)
  if not 1 <= args.duration <= 86400 or not 0.1 <= args.sample_interval <= 5:
    parser.error('duration must be 1..86400 seconds and sample interval 0.1..5 seconds')
  if not 1 <= args.cpu_workers <= (os.cpu_count() or 1) or not 1 <= args.cpu_load <= 100:
    parser.error('CPU workers must fit this machine and CPU load must be 1..100 percent')
  if args.memory_mib < 1 or not 1 <= args.storage_file_mib <= 4096 or not 50 <= args.thermal_limit_c <= 85:
    parser.error('memory must be positive and the thermal stop must be 50..85 C')
  args.components = sorted(set(args.components))
  return args


def run(args):
  manifest = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
  manifest.update(host=platform.node(), platform=platform.platform(), python=platform.python_version())
  if shutil.which('git') and args.openpilot_dir.is_dir():
    revision = subprocess.run(['git', '-C', str(args.openpilot_dir), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=5)
    if revision.returncode == 0:
      manifest['openpilot_revision'] = revision.stdout.strip()
  if args.dry_run:
    print(json.dumps(manifest, indent=2))
    return 0
  if platform.system() != 'Linux':
    raise RuntimeError('Run workloads on Linux; --dry-run is available on other systems.')
  require_offroad()
  validate_resources(args.components, args.memory_mib, memory_info())
  initial_temperatures = temperatures()
  if Path('/AGNOS').exists() and not initial_temperatures:
    raise RuntimeError('No readable thermal sensors; refusing an unmonitored device workload.')
  if initial_temperatures and max(initial_temperatures.values()) >= args.thermal_limit_c:
    raise RuntimeError('Device is already at the thermal stop temperature.')
  output = args.output / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + f'-{time.time_ns() % 1_000_000_000:09d}')
  output.mkdir(parents=True, exist_ok=False)
  (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
  if any(c in args.components for c in ('storage', 'storage-health')):
    health = storage_health(args.storage_dir)
    (output / 'storage-health-before.json').write_text(json.dumps(health, indent=2))
    if args.components == ['storage-health']:
      print(json.dumps({'output': str(output), 'storage_health': health}, indent=2))
      return 1 if health['smart']['status'] in ('failed', 'attention') else 0
  workloads = Workloads(args, output)
  start = time.monotonic()
  previous_cpu = cpu_times()
  summary = {'components': args.components, 'status': 'running', 'samples': 0}
  interrupted = False

  def stop_handler(signum, frame):
    nonlocal interrupted
    interrupted = True

  previous_handlers = {sig: signal.signal(sig, stop_handler) for sig in (signal.SIGINT, signal.SIGTERM)}
  try:
    workloads.start()
    with (output / 'samples.jsonl').open('w', buffering=1) as samples:
      while time.monotonic() - start < args.duration and not interrupted:
        require_offroad()
        temps = temperatures()
        if temps and max(temps.values()) >= args.thermal_limit_c:
          raise RuntimeError('Thermal stop temperature reached.')
        if Path('/AGNOS').exists() and not temps:
          raise RuntimeError('Thermal monitoring became unavailable.')
        info = memory_info()
        if info['available'] < max(256 * MIB, int(info['total'] * 0.08)):
          raise RuntimeError('Available memory fell below the runtime reserve.')
        now_cpu = cpu_times()
        delta = now_cpu[0] - previous_cpu[0]
        usage = 100 * (1 - (now_cpu[1] - previous_cpu[1]) / delta) if delta > 0 else 0
        previous_cpu = now_cpu
        sample = dict(elapsed_s=time.monotonic() - start, cpu_usage_pct=usage, memory_available_mib=info['available'] / MIB,
                      temperatures_c=temps, **workloads.sample())
        samples.write(json.dumps(sample) + '\n')
        summary['samples'] += 1
        if workloads.messages is not None and sample['elapsed_s'] > 20:
          if not workloads.messages.all_alive(list(CAMERA_SERVICES)):
            raise RuntimeError('Camera streams did not become or remain live; see camerad.log.')
        time.sleep(min(args.sample_interval, max(0, args.duration - (time.monotonic() - start))))
    workloads.sample()
    if not interrupted and workloads.messages is not None:
      if not all(workloads.camera_last.get(n, -1) > workloads.camera_first.get(n, -1) for n in CAMERA_SERVICES):
        raise RuntimeError('Not all camera streams produced advancing valid frames; use a longer run or inspect camerad.log.')
    if not interrupted and 'storage' in args.components and workloads.storage_passes == 0:
      raise RuntimeError('No full storage integrity pass completed; use a longer duration or smaller test file.')
    summary['status'] = 'interrupted' if interrupted else 'completed'
  except Exception as exc:
    summary.update(status='stopped', reason=str(exc))
  finally:
    workloads.close()
    for sig, handler in previous_handlers.items():
      signal.signal(sig, handler)
    summary.update(elapsed_s=time.monotonic() - start, camera_first_frames=workloads.camera_first,
                   camera_last_frames=workloads.camera_last, cpu_hashes=sum(v.value for v in workloads.cpu_counters),
                   memory_bytes_written=workloads.memory_counter.value)
    summary.update(storage_passes=workloads.storage_passes, storage_last=workloads.storage_last)
    if any(c in args.components for c in ('storage', 'storage-health')):
      try:
        (output / 'storage-health-after.json').write_text(json.dumps(storage_health(args.storage_dir), indent=2))
      except (OSError, ValueError, subprocess.SubprocessError) as exc:
        summary['storage_health_error'] = str(exc)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2))
  print(json.dumps(dict(output=str(output), **summary), indent=2))
  return 0 if summary['status'] == 'completed' else 1


def main():
  try:
    return run(parse_args())
  except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
    print(f'Benchmark refused: {exc}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  raise SystemExit(main())
