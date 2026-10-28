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
    'updater_weston': 'printf "weston:%s:%s:%s:%s" "$1" "$2" "$XDG_RUNTIME_DIR" "$QT_QPA_PLATFORM"',
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
  env.pop('XDG_RUNTIME_DIR', None)
  result = subprocess.run(['bash', str(tmp_path / source.name), str(script), str(manifest)], env=env,
                          check=True, capture_output=True, text=True)
  suffix = {'legacy': ':wayland-egl', 'weston': ':/var/tmp/weston:wayland-egl'}.get(expected, '')
  assert result.stdout == f'{expected}:{script}:{manifest}{suffix}'


def test_missing_manifest_rejected():
  source = Path(__file__).resolve().parents[1] / 'bootstrap_updater.sh'
  result = subprocess.run(['bash', str(source)], capture_output=True)
  assert result.returncode == 2


def test_stock_12_8_launcher_reaches_weston_prompt(tmp_path):
  """Exercise the real launch/version/selector chain without device writes."""
  repo = Path(__file__).resolve().parents[5]
  checkout = tmp_path / 'stock install'
  updater_dir = checkout / 'openpilot/common/hardware/comma'
  manifest_dir = checkout / 'openpilot/system/hardware/comma'
  updater_dir.mkdir(parents=True)
  manifest_dir.mkdir(parents=True)
  (tmp_path / 'VERSION').write_text('12.8\n')
  (tmp_path / 'AGNOS').touch()
  launcher = (repo / 'launch_chffrplus.sh').read_text()
  launcher = launcher.replace('/VERSION', str(tmp_path / 'VERSION')).replace('/AGNOS', str(tmp_path / 'AGNOS'))
  (checkout / 'launch_chffrplus.sh').write_text(launcher)
  (checkout / 'launch_env.sh').write_text((repo / 'launch_env.sh').read_text())
  source_dir = repo / 'openpilot/common/hardware/comma'
  selector = (source_dir / 'bootstrap_updater.sh').read_text()
  (updater_dir / 'bootstrap_updater.sh').write_text(selector.replace('/usr/comma/updater', str(tmp_path / 'absent_updater')))
  (updater_dir / 'agnos.json').write_text('[]')
  (manifest_dir / 'agnos.json').symlink_to('../../../common/hardware/comma/agnos.json')

  commands = tmp_path / 'bin'
  commands.mkdir()
  for name, body in {
    'sudo': 'printf "SUDO:%s\\n" "$*"',
    'rm': 'exit 0',
    'ln': 'exit 0',
    'systemctl': 'exit 0',
  }.items():
    stub = commands / name
    stub.write_text('#!/bin/sh\n' + body + '\n')
    stub.chmod(0o755)
  flasher = updater_dir / 'agnos.py'
  flasher.write_text('#!/bin/sh\nprintf "VERIFY:%s\\n" "$*"\nexit 1\n')
  flasher.chmod(0o755)
  weston = updater_dir / 'updater_weston'
  # Stop the launcher's infinite retry loop after observing the first prompt.
  weston.write_text('#!/bin/sh\nprintf "WESTON:%s:%s\\n" "$1" "$2"\nkill -TERM "$PPID"\n')
  weston.chmod(0o755)
  env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ['PATH'])
  env.pop('AGNOS_VERSION', None)
  result = subprocess.run(['bash', 'launch_chffrplus.sh'], cwd=checkout, env=env,
                          capture_output=True, text=True, timeout=10)
  assert result.returncode == -15
  manifest = manifest_dir / 'agnos.json'
  assert f'VERIFY:--verify {manifest}' in result.stdout
  assert f'WESTON:{flasher}:{manifest}' in result.stdout
  assert 'SUDO:reboot' not in result.stdout
