import pytest

from opendbc.can import CANPacker
from opendbc.car import gen_empty_fingerprint, structs
from opendbc.car.volkswagen.carstate import CarState
from opendbc.car.volkswagen.interface import CarInterface
from opendbc.car.volkswagen.values import CAR, VolkswagenFlags
from openpilot.cereal import log
from openpilot.selfdrive.car.car_events import CarEvents

EventName = log.OnroadEvent.EventName


def pq_params():
  fp = gen_empty_fingerprint()
  fp[0] = {0xD0: 6}
  fp[1] = dict.fromkeys((0x288, 0x380, 0x480, 0x440, 0x1A0, 0xC2), 8)
  return CarInterface.get_params(CAR.VOLKSWAGEN_PASSAT_NMS, fp, [], False, True, docs=False)


def decoded_cruise(cp, status, main=True):
  state = CarState(cp)
  parsers = state.get_can_parsers(cp)
  state.update(parsers)
  packer = CANPacker('vw_pq')
  frames = [
    packer.make_can_msg('Motor_2', 1, {'MO2_Sta_GRA': status, 'MO2_GRA_Soll': 96}),
    packer.make_can_msg('Motor_5', 1, {'MO5_GRA_Hauptsch': int(main)}),
  ]
  for parser in parsers.values():
    parser.update([(1_000_000_000, frames)])
  out = state.update(parsers)
  out.gearShifter = structs.CarState.GearShifter.drive
  return out


@pytest.mark.parametrize('status', [1, 2])
def test_factory_cruise_can_request_engagement(status):
  cp = pq_params()
  previous = decoded_cruise(cp, 0)
  current = decoded_cruise(cp, status)
  assert cp.flags & VolkswagenFlags.PQ_CC_ONLY
  assert not cp.openpilotLongitudinalControl
  assert current.cruiseState.nonAdaptive
  assert current.cruiseState.enabled
  events = CarEvents(cp).update(current, previous, structs.CarControl())
  assert EventName.pcmEnable in events.names
  assert EventName.wrongCruiseMode not in events.names
  assert EventName.accFaulted not in events.names
  assert EventName.wrongCarMode not in events.names


@pytest.mark.parametrize('status,main', [(0, True), (3, True), (0, False)])
def test_factory_cruise_cancel_and_fault_events_remain(status, main):
  cp = pq_params()
  previous = decoded_cruise(cp, 1)
  current = decoded_cruise(cp, status, main)
  events = CarEvents(cp).update(current, previous, structs.CarControl())
  assert EventName.pcmDisable in events.names
  assert EventName.pcmEnable not in events.names
  if status == 3:
    assert EventName.accFaulted in events.names
  if status == 3 or not main:
    assert EventName.wrongCarMode in events.names


@pytest.mark.parametrize('fault,event', [
  ('doorOpen', EventName.doorOpen),
  ('seatbeltUnlatched', EventName.seatbeltNotLatched),
  ('steerFaultPermanent', EventName.steerUnavailable),
  ('accFaulted', EventName.accFaulted),
  ('parkingBrake', EventName.parkBrake),
])
def test_other_engagement_protections_remain(fault, event):
  cp = pq_params()
  previous = decoded_cruise(cp, 0)
  current = decoded_cruise(cp, 1)
  setattr(current, fault, True)
  events = CarEvents(cp).update(current, previous, structs.CarControl())
  assert event in events.names


@pytest.mark.parametrize('configuration', ['normal_vw', 'not_pcm', 'openpilot_long', 'other_brand'])
def test_nonadaptive_block_remains_outside_factory_cc_mode(configuration):
  cp = pq_params()
  if configuration == 'normal_vw':
    cp.flags &= ~VolkswagenFlags.PQ_CC_ONLY.value
  elif configuration == 'not_pcm':
    cp.pcmCruise = False
  elif configuration == 'openpilot_long':
    cp.openpilotLongitudinalControl = True
  else:
    cp.brand = 'toyota'
  current = structs.CarState()
  current.cruiseState.nonAdaptive = True
  events = CarEvents(cp).create_common_events(current, structs.CarState())
  assert EventName.wrongCruiseMode in events.names
