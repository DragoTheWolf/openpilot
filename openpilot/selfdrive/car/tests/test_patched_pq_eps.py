import pytest

from opendbc.car import gen_empty_fingerprint
from opendbc.car.volkswagen.interface import CarInterface
from opendbc.car.volkswagen.values import CAR, VolkswagenFlags
from openpilot.common.params import Params, ParamKeyFlag
from openpilot.selfdrive.car.volkswagen import PATCHED_EPS_PARAM, apply_patched_pq_eps, set_patched_pq_eps


@pytest.fixture
def params(tmp_path):
  return Params(str(tmp_path))


def pq_params():
  fp = gen_empty_fingerprint()
  fp[0] = {0xD0: 6}
  fp[1] = dict.fromkeys((0x288, 0x380, 0x480, 0x440, 0x1A0, 0xC2), 8)
  return CarInterface.get_params(CAR.VOLKSWAGEN_PASSAT_NMS, fp, [], False, True, docs=False)


def test_patched_eps_is_opt_in_and_persistent(params):
  assert not params.get_bool(PATCHED_EPS_PARAM)
  params.put('CarParamsCache', b'old parameters', block=True)
  set_patched_pq_eps(params, True)
  assert params.get('CarParamsCache') is None
  params.clear_all(ParamKeyFlag.CLEAR_ON_MANAGER_START)
  assert Params(params.d).get_bool(PATCHED_EPS_PARAM)
  set_patched_pq_eps(params, False)
  assert not Params(params.d).get_bool(PATCHED_EPS_PARAM)


@pytest.mark.parametrize('enabled', [False, True])
def test_only_steering_speed_changes_and_reaches_existing_interface(params, enabled):
  cp = pq_params()
  interface = CarInterface(cp)
  before = cp.to_dict()
  assert cp.minSteerSpeed == pytest.approx(50 / 3.6)
  set_patched_pq_eps(params, enabled)
  apply_patched_pq_eps(cp, params)
  expected = 0 if enabled else 50 / 3.6
  assert cp.minSteerSpeed == pytest.approx(expected)
  assert interface.CS.CP.minSteerSpeed == pytest.approx(expected)
  assert interface.CC.CP.minSteerSpeed == pytest.approx(expected)
  for speed in (0, 1, 5, 10, 13):
    assert interface.CS.update_low_speed_alert(speed) == (not enabled)
  after = cp.to_dict()
  before.pop('minSteerSpeed')
  after.pop('minSteerSpeed')
  assert before == after  # Includes safety, minimum engagement speed, cruise, and standstill policy.


@pytest.mark.parametrize('configuration', ['other_model', 'other_brand', 'not_pq', 'not_cc', 'not_pcm', 'openpilot_long'])
def test_patched_eps_does_not_apply_to_other_configurations(params, configuration):
  cp = pq_params()
  if configuration == 'other_model':
    cp.carFingerprint = str(CAR.VOLKSWAGEN_JETTA_MK6)
  elif configuration == 'other_brand':
    cp.brand = 'toyota'
  elif configuration == 'not_pq':
    cp.flags &= ~VolkswagenFlags.PQ.value
  elif configuration == 'not_cc':
    cp.flags &= ~VolkswagenFlags.PQ_CC_ONLY.value
  elif configuration == 'not_pcm':
    cp.pcmCruise = False
  else:
    cp.openpilotLongitudinalControl = True
  before = cp.to_dict()
  set_patched_pq_eps(params, True)
  apply_patched_pq_eps(cp, params)
  assert cp.to_dict() == before
