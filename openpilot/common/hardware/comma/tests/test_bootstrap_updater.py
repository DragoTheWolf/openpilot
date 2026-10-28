import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('weston_ready,system_available,expected', [
  (True, True, 'weston'), (True, False, 'weston'),
  (False, True, 'system'), (False, False, 'legacy'),
])
def test_updater_selection(tmp_path, weston_ready, system_available, expected):
  source = Path(__file__).resolve().parents[1] / 'bootstrap_updater.sh'
  system_updater = tmp_path / 'system_updater'
  (tmp_path / source.name).write_text(source.read_text().replace('/usr/comma/updater', str(system_updater)))
  # These stubs only print the selected route; no updater or flashing runs.
  for name, body in {
    'systemctl': f'exit {0 if weston_ready else 1}',
    'updater': 'printf "weston:%s:%s" "$1" "$2"',
    'updater_magic': 'printf "legacy:%s:%s:%s" "$1" "$2" "$QT_QPA_PLATFORM"',
  }.items():
    stub = tmp_path / name
    stub.write_text('#!/bin/sh\n' + body + '\n')
    stub.chmod(0o755)
  if system_available:
    system_updater.write_text('#!/bin/sh\nprintf "system:%s:%s" "$1" "$2"\n')
    system_updater.chmod(0o755)
  script, manifest = tmp_path / 'agnos with spaces.py', tmp_path / 'manifest with spaces.json'
  script.touch()
  manifest.touch()
  env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'])
  result = subprocess.run(['bash', str(tmp_path / source.name), str(script), str(manifest)], env=env,
                          check=True, capture_output=True, text=True)
  suffix = ':wayland-egl' if expected == 'legacy' else ''
  assert result.stdout == f'{expected}:{script}:{manifest}{suffix}'


def test_missing_manifest_rejected():
  source = Path(__file__).resolve().parents[1] / 'bootstrap_updater.sh'
  result = subprocess.run(['bash', str(source)], capture_output=True)
  assert result.returncode == 2
