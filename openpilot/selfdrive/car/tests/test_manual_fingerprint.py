import os
from unittest.mock import patch

import pytest

from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car import car_helpers
from opendbc.car.volkswagen.values import CAR, VolkswagenFlags
from openpilot.common.params import Params, ParamKeyFlag
from openpilot.selfdrive.car.manual_fingerprint import MANUAL_CAR_PARAM, manual_car_index, manual_fingerprint, set_manual_car


@pytest.fixture
def params(tmp_path):
  return Params(str(tmp_path))


def test_selection_persists_and_invalidates_cache(params):
  assert manual_car_index(params) == 1  # Preserve this fork's existing NMS default.
  params.put("CarParamsCache", b"old vehicle", block=True)
  set_manual_car(params, 0)
  assert params.get("CarParamsCache") is None
  params.clear_all(ParamKeyFlag.CLEAR_ON_MANAGER_START)
  assert manual_car_index(Params(params.d)) == 0
  set_manual_car(params, 1)
  assert params.get(MANUAL_CAR_PARAM) == str(CAR.VOLKSWAGEN_PASSAT_NMS)
  assert manual_car_index(Params(params.d)) == 1


def test_manual_environment_is_restored_on_failure(params):
  with patch.dict(os.environ, {"FINGERPRINT": "external", "SKIP_FW_QUERY": "external"}):
    with pytest.raises(RuntimeError), manual_fingerprint(params):
      assert os.environ["FINGERPRINT"] == str(CAR.VOLKSWAGEN_PASSAT_NMS)
      assert os.environ["SKIP_FW_QUERY"] == "1"
      raise RuntimeError("initialization failed")
    assert os.environ["FINGERPRINT"] == "external"
    assert os.environ["SKIP_FW_QUERY"] == "external"


@pytest.mark.parametrize("selection", ["AUTO", "not a supported model"])
def test_automatic_and_invalid_selection_do_not_force_vehicle(params, selection, monkeypatch):
  monkeypatch.delenv("FINGERPRINT", raising=False)
  monkeypatch.delenv("SKIP_FW_QUERY", raising=False)
  params.put(MANUAL_CAR_PARAM, selection, block=True)
  with manual_fingerprint(params):
    assert "FINGERPRINT" not in os.environ
    assert "SKIP_FW_QUERY" not in os.environ


@pytest.mark.parametrize("has_can", [True, False])
def test_manual_selection_uses_can_configuration_without_fw_query(params, monkeypatch, has_can):
  fp = gen_empty_fingerprint()
  if has_can:
    fp[0] = {0xD0: 6}
    fp[1] = dict.fromkeys((0x288, 0x380, 0x480, 0x440, 0x1A0, 0xC2), 8)
  calls = []

  def observed_can(_):
    calls.append(True)
    return None, fp

  def unexpected_query(*args, **kwargs):
    pytest.fail("Manual selection must not require VIN/FW queries")

  monkeypatch.setattr(car_helpers, "can_fingerprint", observed_can)
  monkeypatch.setattr(car_helpers, "get_vin", unexpected_query)
  monkeypatch.setattr(car_helpers, "get_present_ecus", unexpected_query)
  monkeypatch.setattr(car_helpers, "get_fw_versions_ordered", unexpected_query)
  with manual_fingerprint(params):
    interface = car_helpers.get_car(list, lambda _: None, lambda _: None, True, True)
  assert calls == [True]
  cp = interface.CP
  assert cp.carFingerprint == str(CAR.VOLKSWAGEN_PASSAT_NMS)
  assert cp.fingerprintSource == structs.CarParams.FingerprintSource.fixed
  assert bool(cp.flags & VolkswagenFlags.PQ_CC_ONLY) == has_can
  assert cp.dashcamOnly == (not has_can)
  if has_can:
    assert not cp.openpilotLongitudinalControl
