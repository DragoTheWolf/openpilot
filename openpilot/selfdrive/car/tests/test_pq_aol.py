import pytest

from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car.volkswagen.interface import CarInterface
from opendbc.car.volkswagen.values import CAR, VolkswagenFlags, VolkswagenSafetyFlags
from openpilot.common.params import Params
from openpilot.cereal import log
from openpilot.selfdrive.car.car_events import CarEvents, brake_disengages
from openpilot.selfdrive.car.volkswagen import AOL_PARAM, apply_pq_aol, pq_aol_enabled, set_pq_aol
from openpilot.selfdrive.selfdrived.state import StateMachine
from openpilot.selfdrive.selfdrived.events import ET, AudibleAlert

EventName = log.OnroadEvent.EventName
Button = structs.CarState.ButtonEvent.Type


@pytest.fixture
def configuration(tmp_path):
  fp = gen_empty_fingerprint()
  fp[0] = {0xD0: 6}
  fp[1] = dict.fromkeys((0x288, 0x380, 0x480, 0x440, 0x1A0, 0xC2), 8)
  cp = CarInterface.get_params(CAR.VOLKSWAGEN_PASSAT_NMS, fp, [], False, True, docs=False)
  params = Params(str(tmp_path))
  return cp, params


def state(main=True, cruise=False, buttons=(), **fields):
  cs = structs.CarState()
  cs.gearShifter = structs.CarState.GearShifter.drive
  cs.cruiseState.available = main
  cs.cruiseState.enabled = cruise
  cs.cruiseState.nonAdaptive = True
  cs.buttonEvents = [structs.CarState.ButtonEvent(type=kind, pressed=pressed) for kind, pressed in buttons]
  for name, value in fields.items():
    setattr(cs, name, value)
  return cs


def enable_aol(cp, params):
  set_pq_aol(params, True)
  apply_pq_aol(cp, params)


def test_aol_opt_in_and_only_lateral_permissions(configuration):
  cp, params = configuration
  before = cp.to_dict()
  assert not params.get_bool(AOL_PARAM)
  apply_pq_aol(cp, params)
  assert cp.to_dict() == before
  enable_aol(cp, params)
  assert pq_aol_enabled(cp)
  assert cp.flags == before['flags'] | VolkswagenFlags.PQ_AOL
  assert cp.safetyConfigs[-1].safetyParam == before['safetyConfigs'][-1]['safetyParam'] | VolkswagenSafetyFlags.PQ_AOL
  assert cp.pcmCruise and not cp.openpilotLongitudinalControl
  assert cp.minSteerSpeed == before['minSteerSpeed']


def test_cruise_engages_then_brake_leaves_aol_steering(configuration):
  cp, params = configuration
  enable_aol(cp, params)
  events = CarEvents(cp)
  sm = StateMachine()
  cs = state(main=True)
  assert sm.update(events.update(cs, state(main=False), structs.CarControl())) == (False, False)
  engaged = state(cruise=True)
  assert sm.update(events.update(engaged, cs, structs.CarControl())) == (True, True)
  braking = state(brakePressed=True)
  assert not brake_disengages(cp, braking, engaged, True)
  assert sm.update(events.update(braking, engaged, structs.CarControl(enabled=True))) == (True, True)
  assert sm.update(events.update(cs, braking, structs.CarControl(enabled=True))) == (True, True)
  assert sm.update(events.update(state(main=False), cs, structs.CarControl())) == (False, False)


def test_default_mode_still_requires_factory_cruise(configuration):
  cp, _ = configuration
  events = CarEvents(cp).update(state(), state(main=False), structs.CarControl())
  assert EventName.pcmDisable in events.names
  assert EventName.buttonEnable not in events.names
  assert brake_disengages(cp, state(brakePressed=True), state(), True)


def test_main_switch_engages_once_and_main_off_disengages(configuration):
  cp, params = configuration
  enable_aol(cp, params)
  events, sm = CarEvents(cp), StateMachine()
  off, on = state(main=False), state()
  events.update(off, off, structs.CarControl())
  assert sm.update(events.update(on, off, structs.CarControl())) == (True, True)
  assert sm.update(events.update(off, on, structs.CarControl(enabled=True))) == (False, False)
  assert EventName.buttonEnable not in events.update(off, off, structs.CarControl()).names


@pytest.mark.parametrize('block', ['brakePressed', 'accFaulted', 'blockPcmEnable'])
def test_main_switch_blocked_and_no_auto_retry(configuration, block):
  cp, params = configuration
  enable_aol(cp, params)
  events = CarEvents(cp)
  off = state(main=False)
  events.update(off, off, structs.CarControl())
  blocked = state(**{block: True})
  assert EventName.buttonEnable not in events.update(blocked, off, structs.CarControl()).names
  assert EventName.buttonEnable not in events.update(state(), blocked, structs.CarControl()).names


def test_main_already_on_at_startup_does_not_engage(configuration):
  cp, params = configuration
  enable_aol(cp, params)
  events = CarEvents(cp)
  assert EventName.buttonEnable not in events.update(state(), state(main=False), structs.CarControl()).names


@pytest.mark.parametrize('gear', [structs.CarState.GearShifter.park, structs.CarState.GearShifter.reverse,
                                structs.CarState.GearShifter.neutral, structs.CarState.GearShifter.unknown])
def test_gear_change_disables_aol_without_urgent_stopped_alert(configuration, gear):
  cp, params = configuration
  enable_aol(cp, params)
  events, sm = CarEvents(cp), StateMachine()
  off, on = state(main=False), state()
  events.update(off, off, structs.CarControl())
  assert sm.update(events.update(on, off, structs.CarControl())) == (True, True)
  non_drive = state(gearShifter=gear, standstill=True)
  result = events.update(non_drive, on, structs.CarControl(enabled=True))
  assert EventName.wrongGear in result.names
  assert sm.update(result) == (False, False)
  alerts = result.create_alerts(sm.current_alert_types, [cp, non_drive, None, True, 0, 0])
  assert all(a.audible_alert not in (AudibleAlert.warningImmediate, AudibleAlert.warningSoft) for a in alerts)
  assert EventName.buttonEnable not in events.update(on, non_drive, structs.CarControl()).names
  # SET/RES and switch requests in a non-driving gear remain blocked.
  events.update(state(main=False, gearShifter=gear), non_drive, structs.CarControl())
  assert EventName.buttonEnable not in events.update(non_drive, state(main=False, gearShifter=gear), structs.CarControl()).names


@pytest.mark.parametrize('aol,stopped,speed', [(False, True, 0), (True, False, 2), (True, True, 2)])
def test_reverse_urgent_alert_preserved_outside_stopped_aol(configuration, aol, stopped, speed):
  cp, params = configuration
  if aol:
    enable_aol(cp, params)
  cs = state(gearShifter=structs.CarState.GearShifter.reverse, standstill=stopped, vEgo=speed)
  result = CarEvents(cp).update(cs, state(), structs.CarControl(enabled=True))
  alerts = result.create_alerts([ET.USER_DISABLE], [cp, cs, None, True, 0, 0])
  assert any(a.audible_alert == AudibleAlert.warningImmediate for a in alerts)


def test_non_drive_warning_while_moving_is_preserved(configuration):
  cp, params = configuration
  enable_aol(cp, params)
  cs = state(gearShifter=structs.CarState.GearShifter.neutral, standstill=False, vEgo=5)
  result = CarEvents(cp).update(cs, state(), structs.CarControl(enabled=True))
  assert EventName.pcmDisable not in result.names
  assert result.contains(ET.SOFT_DISABLE)
  alerts = result.create_alerts([ET.SOFT_DISABLE], [cp, cs, None, True, 100, 0])
  assert any(a.audible_alert == AudibleAlert.warningSoft for a in alerts)


@pytest.mark.parametrize('configuration_name', ['not_pq', 'not_cc', 'other_model', 'other_brand', 'not_pcm', 'longitudinal'])
def test_aol_does_not_apply_outside_this_port(configuration, configuration_name):
  cp, params = configuration
  if configuration_name == 'not_pq':
    cp.flags &= ~VolkswagenFlags.PQ.value
  elif configuration_name == 'not_cc':
    cp.flags &= ~VolkswagenFlags.PQ_CC_ONLY.value
  elif configuration_name == 'other_model':
    cp.carFingerprint = str(CAR.VOLKSWAGEN_JETTA_MK6)
  elif configuration_name == 'other_brand':
    cp.brand = 'toyota'
  elif configuration_name == 'not_pcm':
    cp.pcmCruise = False
  else:
    cp.openpilotLongitudinalControl = True
  before = cp.to_dict()
  enable_aol(cp, params)
  assert cp.to_dict() == before
  assert not pq_aol_enabled(cp)


def test_fault_recovery_does_not_auto_engage(configuration):
  cp, params = configuration
  enable_aol(cp, params)
  previous = state(main=False, accFaulted=True)
  recovered = state(main=True)
  result = CarEvents(cp).update(recovered, previous, structs.CarControl())
  assert EventName.buttonEnable not in result.names


@pytest.mark.parametrize('button', [Button.setCruise, Button.resumeCruise])
def test_reengagement_on_deliberate_release(configuration, button):
  cp, params = configuration
  enable_aol(cp, params)
  events = CarEvents(cp)
  neutral = state()
  press = state(buttons=[(button, True)])
  assert EventName.buttonEnable not in events.update(press, neutral, structs.CarControl()).names
  release = state(buttons=[(button, False)])
  assert EventName.buttonEnable in events.update(release, press, structs.CarControl()).names


@pytest.mark.parametrize('fault', ['brakePressed', 'accFaulted'])
def test_pedals_and_faults_cannot_start_aol_or_arm_stale_buttons(configuration, fault):
  cp, params = configuration
  enable_aol(cp, params)
  events = CarEvents(cp)
  neutral = state()
  blocked = state(**{fault: True}, buttons=[(Button.setCruise, True)])
  result = events.update(blocked, neutral, structs.CarControl())
  assert EventName.buttonEnable not in result.names
  if fault == 'accFaulted':
    assert EventName.pcmDisable in result.names
  else:
    assert brake_disengages(cp, blocked, neutral, False)
  release = state(buttons=[(Button.setCruise, False)])
  assert EventName.buttonEnable not in events.update(release, blocked, structs.CarControl()).names


def test_cancel_dominates_set_release(configuration):
  cp, params = configuration
  enable_aol(cp, params)
  events = CarEvents(cp)
  neutral = state()
  press = state(buttons=[(Button.setCruise, True)])
  events.update(press, neutral, structs.CarControl())
  cancel = state(buttons=[(Button.setCruise, False), (Button.cancel, True)])
  result = events.update(cancel, press, structs.CarControl())
  assert EventName.buttonCancel in result.names
  assert EventName.buttonEnable not in result.names
  assert EventName.buttonEnable not in events.update(neutral, cancel, structs.CarControl()).names


@pytest.mark.parametrize('fault,event', [('doorOpen', EventName.doorOpen), ('seatbeltUnlatched', EventName.seatbeltNotLatched),
                                       ('steerFaultPermanent', EventName.steerUnavailable)])
def test_existing_faults_block_aol_engagement(configuration, fault, event):
  cp, params = configuration
  enable_aol(cp, params)
  result = CarEvents(cp).update(state(**{fault: True}), state(main=False), structs.CarControl())
  assert event in result.names
  assert StateMachine().update(result) == (False, False)


def test_controller_uses_hca7_and_no_longitudinal_commands(configuration):
  cp, params = configuration
  enable_aol(cp, params)
  interface = CarInterface(cp)
  interface.CS.update(interface.can_parsers)
  interface.CS.out = state()
  cc = structs.CarControl(enabled=True, latActive=True)
  cc.actuators.torque = 0.2
  _, sends = interface.CC.update(cc.as_reader(), interface.CS, 0)
  hca = next(msg for msg in sends if msg[0] == 0xD2)
  assert (hca[1][1] >> 4) & 0xF == 7
  assert not {0x368, 0x56A, 0x38A} & {msg[0] for msg in sends}
  cc.latActive = False
  interface.CC.update(cc.as_reader(), interface.CS, 10_000_000)
  _, sends = interface.CC.update(cc.as_reader(), interface.CS, 20_000_000)
  hca = next(msg for msg in sends if msg[0] == 0xD2)
  assert (hca[1][1] >> 4) & 0xF == 3
