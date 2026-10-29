from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pyray as rl
from opendbc.car import structs
from opendbc.car.volkswagen.values import CAR, VolkswagenFlags
from openpilot.cereal import log
from openpilot.selfdrive.ui.ui_state import UIState, UIStatus
from openpilot.selfdrive.ui.onroad import augmented_road_view as road


def border_state(cruise=False, active=True, lat_active=True, healthy=True, status=UIStatus.ENGAGED,
                 alert_status=log.SelfdriveState.AlertStatus.normal, aol=True):
  cp = structs.CarParams(brand='volkswagen', carFingerprint=CAR.VOLKSWAGEN_PASSAT_NMS,
                        flags=int(VolkswagenFlags.PQ | VolkswagenFlags.PQ_CC_ONLY | (VolkswagenFlags.PQ_AOL if aol else 0)),
                        pcmCruise=True)
  class Messages(dict):
    def all_checks(self, services):
      return healthy
  messages = Messages(selfdriveState=SimpleNamespace(active=active, alertStatus=alert_status),
                      carState=SimpleNamespace(cruiseState=SimpleNamespace(enabled=cruise)),
                      carControl=SimpleNamespace(latActive=lat_active))
  result = SimpleNamespace(CP=cp, status=status, sm=messages)
  result.aol_without_cruise = UIState.aol_without_cruise.fget(result)
  return result


@pytest.mark.parametrize('changes,expected', [({}, True), ({'cruise': True}, False), ({'active': False}, False),
                                           ({'lat_active': False}, False), ({'healthy': False}, False),
                                           ({'aol': False}, False), ({'status': UIStatus.OVERRIDE}, False),
                                           ({'status': UIStatus.DISENGAGED}, False),
                                           ({'alert_status': log.SelfdriveState.AlertStatus.critical}, False)])
def test_lateral_only_indicator_requires_active_healthy_aol(changes, expected):
  assert UIState.aol_lateral_only.fget(border_state(**changes)) == expected


@pytest.mark.parametrize('lateral_only', [False, True])
def test_border_color_and_bottom_strip(lateral_only):
  fake_state = SimpleNamespace(status=UIStatus.ENGAGED, aol_lateral_only=lateral_only, aol_without_cruise=lateral_only)
  rect = rl.Rectangle(0, 0, 2160, 1080)
  with patch.object(road, 'ui_state', fake_state), patch.object(rl, 'draw_rectangle_lines_ex'), \
       patch.object(rl, 'draw_rectangle_rounded_lines_ex') as border, patch.object(rl, 'draw_rectangle_rounded') as strip:
    road.AugmentedRoadView._draw_border(None, rect)
  color = border.call_args.args[-1]
  expected = road.BORDER_COLORS[UIStatus.DISENGAGED if lateral_only else UIStatus.ENGAGED]
  assert (color.r, color.g, color.b) == (expected.r, expected.g, expected.b)
  assert strip.call_count == int(lateral_only)
  if lateral_only:
    strip_rect, _, _, strip_color = strip.call_args.args
    assert strip_rect.y > rect.height * 0.9
    assert strip_rect.width < rect.width
    assert (strip_color.r, strip_color.g, strip_color.b) == (0x60, 0xB5, 0xFF)
  else:
    assert (color.r, color.g, color.b) == (0x16, 0x4B, 0x89)


def test_inactive_aol_does_not_show_full_engaged_border():
  fake_state = SimpleNamespace(status=UIStatus.ENGAGED, aol_lateral_only=False, aol_without_cruise=True)
  with patch.object(road, 'ui_state', fake_state), patch.object(rl, 'draw_rectangle_lines_ex'), \
       patch.object(rl, 'draw_rectangle_rounded_lines_ex') as border, patch.object(rl, 'draw_rectangle_rounded') as strip:
    road.AugmentedRoadView._draw_border(None, rl.Rectangle(0, 0, 2160, 1080))
  color = border.call_args.args[-1]
  expected = road.BORDER_COLORS[UIStatus.DISENGAGED]
  assert (color.r, color.g, color.b) == (expected.r, expected.g, expected.b)
  strip.assert_not_called()
