import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

spec = importlib.util.spec_from_file_location('bench', Path(__file__).with_name('bench.py'))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_components_are_explicit_and_independent(tmp_path):
  args = bench.parse_args(['--components', 'cpu', 'memory', '--dry-run', '--output', str(tmp_path)])
  with patch.object(bench.Workloads, 'start_cameras') as camera, patch.object(bench.mp, 'Process') as process:
    workloads = bench.Workloads(args, tmp_path)
    try:
      workloads.start()
      camera.assert_not_called()
      targets = [c.kwargs['target'] for c in process.call_args_list]
      assert targets.count(bench.cpu_worker) == args.cpu_workers
      assert targets.count(bench.memory_worker) == 1
      assert bench.storage_worker not in targets
    finally:
      # No actual subprocesses were created in this selection test.
      workloads.workers = []
      workloads.close()


def test_dry_run_never_starts_workloads_or_writes_results(tmp_path, capsys):
  output = tmp_path / 'not-created'
  args = bench.parse_args(['--components', 'cpu', 'memory', '--dry-run', '--output', str(output)])
  with patch.object(bench, 'Workloads') as workloads:
    assert bench.run(args) == 0
    workloads.assert_not_called()
  assert not output.exists()
  assert json.loads(capsys.readouterr().out)['components'] == ['cpu', 'memory']


def test_device_refuses_onroad_or_unknown_state(tmp_path):
  hardware = tmp_path / 'AGNOS'
  hardware.touch()
  params = tmp_path / 'params'
  params.mkdir()
  with pytest.raises(RuntimeError):
    bench.require_offroad(hardware, params)
  (params / 'IsOffroad').write_text('0')
  with pytest.raises(RuntimeError):
    bench.require_offroad(hardware, params)
  (params / 'IsOffroad').write_text('1')
  bench.require_offroad(hardware, params)


def test_memory_reserve_and_non_memory_selection():
  info = {'total': 4 * 1024 * bench.MIB, 'available': 1024 * bench.MIB}
  with pytest.raises(ValueError):
    bench.validate_resources(['memory'], 1024, info)
  bench.validate_resources(['cpu'], 100000, info)


def test_temperature_stop_cleans_up_only_its_workloads(tmp_path):
  args = bench.parse_args(['--components', 'cpu', '--duration', '1', '--output', str(tmp_path)])
  fake = Mock(camera_first={}, camera_last={}, cpu_counters=[], memory_counter=Mock(value=0),
              storage_passes=0, storage_last=None)
  with patch.object(bench, 'Workloads', return_value=fake), patch.object(bench, 'temperatures', side_effect=[{'cpu': 30}, {'cpu': 85}]):
    assert bench.run(args) == 1
  fake.close.assert_called_once()
  summary = json.loads(next(tmp_path.glob('*/summary.json')).read_text())
  assert summary['status'] == 'stopped'
  assert 'Thermal' in summary['reason']


def test_transition_onroad_stops_and_cleans_up(tmp_path):
  args = bench.parse_args(['--components', 'cpu', '--duration', '1', '--output', str(tmp_path)])
  fake = Mock(camera_first={}, camera_last={}, cpu_counters=[], memory_counter=Mock(value=0),
              storage_passes=0, storage_last=None)
  with patch.object(bench, 'Workloads', return_value=fake), \
       patch.object(bench, 'require_offroad', side_effect=[None, RuntimeError('Device went onroad')]):
    assert bench.run(args) == 1
  fake.close.assert_called_once()
  summary = json.loads(next(tmp_path.glob('*/summary.json')).read_text())
  assert summary['status'] == 'stopped'
  assert 'onroad' in summary['reason']


def test_storage_health_only_has_no_workload(tmp_path):
  args = bench.parse_args(['--components', 'storage-health', '--storage-dir', str(tmp_path), '--output', str(tmp_path / 'results')])
  with patch.object(bench, 'Workloads') as workloads:
    assert bench.run(args) == 0
    workloads.assert_not_called()
  assert not list(tmp_path.glob('openpilot-bench-*'))


def test_small_storage_run_verifies_data_and_removes_own_file(tmp_path):
  original = tmp_path / 'existing-recording'
  original.write_bytes(b'preserve this recording')
  args = bench.parse_args(['--components', 'storage', '--duration', '1', '--sample-interval', '0.1',
                           '--storage-dir', str(tmp_path), '--storage-file-mib', '2', '--output', str(tmp_path / 'results')])
  assert bench.run(args) == 0
  summary = json.loads(next((tmp_path / 'results').glob('*/summary.json')).read_text())
  assert summary['storage_passes'] > 0
  assert summary['storage_last']['integrity_ok']
  assert not list(tmp_path.glob('openpilot-bench-*'))
  assert original.read_bytes() == b'preserve this recording'


def test_camera_not_silently_enabled_with_storage(tmp_path):
  args = bench.parse_args(['--components', 'storage', '--output', str(tmp_path)])
  with patch.object(bench.Workloads, 'start_cameras') as camera, patch.object(bench.mp, 'Process') as process:
    workloads = bench.Workloads(args, tmp_path)
    try:
      workloads.start()
      camera.assert_not_called()
      assert process.call_args.kwargs['target'] is bench.storage_worker
    finally:
      workloads.workers = []
      workloads.close()


def test_failed_smart_health_is_reported_as_failed(tmp_path):
  mount = Mock(returncode=0, stdout=json.dumps({'filesystems': [{'source': '/dev/nvme0n1', 'target': str(tmp_path)}]}))
  smart = Mock(returncode=8, stdout=json.dumps({'smart_status': {'passed': False}}))
  with patch.object(bench.shutil, 'which', return_value='/test/tool'), patch.object(bench.subprocess, 'run', side_effect=[mount, smart]):
    result = bench.storage_health(tmp_path)
  assert result['smart']['status'] == 'failed'


def test_smart_permission_failure_is_not_healthy(tmp_path):
  mount = Mock(returncode=0, stdout=json.dumps({'filesystems': [{'source': '/dev/nvme0n1', 'target': str(tmp_path)}]}))
  smart = Mock(returncode=2, stdout=json.dumps({'smartctl': {'messages': [{'string': 'Permission denied'}]}}))
  with patch.object(bench.shutil, 'which', return_value='/test/tool'), patch.object(bench.subprocess, 'run', side_effect=[mount, smart]):
    assert bench.storage_health(tmp_path)['smart']['status'] == 'unavailable'
