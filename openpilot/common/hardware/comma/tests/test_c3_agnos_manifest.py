import json
import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from openpilot.common.hardware.comma import agnos


@pytest.fixture
def manifests(tmp_path, monkeypatch):
  generic = tmp_path / 'agnos.json'
  c3 = tmp_path / 'agnos_c3.json'
  generic.write_text(json.dumps([{'name': 'modern', 'full_check': False}]))
  c3.write_text(json.dumps([{'name': 'original', 'full_check': False}]))
  monkeypatch.setattr(agnos, 'get_device_model', lambda: 'comma tici')
  return generic, c3


@pytest.mark.parametrize('model,expected', [
  ('comma tici', 'agnos_c3.json'), ('comma three', 'agnos_c3.json'),
  ('comma tizi', 'agnos.json'), ('comma mici', 'agnos.json'), ('', 'agnos.json'),
])
def test_manifest_selection(manifests, monkeypatch, model, expected):
  monkeypatch.setattr(agnos, 'get_device_model', lambda: model)
  assert Path(agnos.select_agnos_manifest(str(manifests[0]))).name == expected


def test_compatibility_symlink_and_explicit_c3_manifest(manifests, tmp_path):
  generic, c3 = manifests
  alias_dir = tmp_path / 'compatibility'
  alias_dir.mkdir()
  alias = alias_dir / 'agnos.json'
  alias.symlink_to(generic)
  assert agnos.select_agnos_manifest(str(alias)) == str(c3)
  assert agnos.select_agnos_manifest(str(c3)) == str(c3)


def test_original_c3_fails_without_compatible_manifest(manifests):
  generic, c3 = manifests
  c3.unlink()
  with pytest.raises(FileNotFoundError, match='Original comma 3 requires'):
    agnos.select_agnos_manifest(str(generic))


def test_verify_uses_original_c3_partitions(manifests, monkeypatch):
  verify = Mock(return_value=True)
  monkeypatch.setattr(agnos, 'verify_partition', verify)
  assert agnos.verify_agnos_update(str(manifests[0]), 1)
  verify.assert_called_once_with(1, {'name': 'original', 'full_check': False})


def test_background_flash_uses_original_c3_partitions(manifests, monkeypatch):
  flash = Mock()
  command = Mock()
  monkeypatch.setattr(agnos, 'flash_partition', flash)
  monkeypatch.setattr(agnos.subprocess, 'run', command)
  agnos.flash_agnos_update(str(manifests[0]), 1, logging)
  flash.assert_called_once_with(1, {'name': 'original', 'full_check': False}, logging, False)
  command.assert_called_once_with('abctl --set_unbootable 1', shell=True)


def test_swap_uses_original_c3_partitions(manifests, monkeypatch):
  clear = Mock()
  monkeypatch.setattr(agnos, 'clear_partition_hash', clear)
  monkeypatch.setattr(agnos.subprocess, 'check_output', Mock(return_value='lun as boot lun'))
  agnos.swap(str(manifests[0]), 1, logging)
  clear.assert_called_once_with(1, {'name': 'original', 'full_check': False})


def test_c3_boot_chain_and_current_system_are_pinned():
  directory = Path(agnos.__file__).parent
  generic = {p['name']: p for p in json.loads((directory / 'agnos.json').read_text())}
  original = {p['name']: p for p in json.loads((directory / 'agnos_c3.json').read_text())}
  # Official v0.10.0 / AGNOS 12.8 boot-chain artifacts, including comma_tici.dtb.
  boot_hashes = {
    'xbl': 'effa23294138e2297b85a5b482a885184c437b5ab25d74f2a62d4fce4e68f63b',
    'xbl_config': '63d019efed684601f145ef37628e62c8da73f5053a8e51d7de09e72b8b11f97c',
    'abl': '32a2174b5f764e95dfc54cf358ba01752943b1b3b90e626149c3da7d5f1830b6',
    'aop': '21370172e590bd4ea907a558bcd6df20dc7a6c7d38b8e62fdde18f4a512ba9e9',
    'devcfg': 'd7d7e52963bbedbbf8a7e66847579ca106a0a729ce2cf60f4b8d8ea4b535d620',
    'boot': '0191529aa97d90d1fa04b472d80230b777606459e1e1e9e2323c9519839827b4',
  }
  assert set(original) == set(generic) == set(boot_hashes) | {'system'}
  assert original['system'] == generic['system']
  for name, digest in boot_hashes.items():
    partition = original[name]
    assert partition['hash'] == partition['hash_raw'] == digest
    assert partition['full_check'] and partition['has_ab'] and not partition['sparse']
