import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('weston_ready,expected', [(True, 'weston'), (False, 'magic')])
def test_updater_selection(tmp_path, weston_ready, expected):
  source = Path(__file__).resolve().parents[1] / 'bootstrap_updater.sh'
  shutil.copyfile(source, tmp_path / source.name)
  # These stubs only print the selected route; no updater or flashing runs.
  for name, body in {
    'systemctl': f'exit {0 if weston_ready else 1}',
    'updater': 'printf "weston:%s:%s" "$1" "$2"',
    'updater_magic': 'printf "magic:%s:%s" "$1" "$2"',
  }.items():
    stub = tmp_path / name
    stub.write_text('#!/bin/sh\n' + body + '\n')
    stub.chmod(0o755)
  script, manifest = tmp_path / 'agnos with spaces.py', tmp_path / 'manifest with spaces.json'
  script.touch()
  manifest.touch()
  env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'])
  result = subprocess.run(['bash', str(tmp_path / source.name), str(script), str(manifest)], env=env,
                          check=True, capture_output=True, text=True)
  assert result.stdout == f'{expected}:{script}:{manifest}'


def test_missing_manifest_rejected():
  source = Path(__file__).resolve().parents[1] / 'bootstrap_updater.sh'
  result = subprocess.run(['bash', str(source)], capture_output=True)
  assert result.returncode == 2
