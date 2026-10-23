from unittest.mock import Mock

from openpilot.common.hardware.comma.amplifier import Amplifier, CONFIG


def test_original_c3_speaker_tuning():
  amp = Amplifier()
  amp.set_configs = Mock(return_value=True)
  assert amp.initialize_configuration('tici')
  configs = amp.set_configs.call_args.args[0]
  # Original C3's single-speaker route uses equalization and different volume.
  eq = next(c for c in configs if c.name == 'DAI2 EQ enable')
  volume = next(c for c in configs if c.name == 'Right speaker output volume')
  assert eq.value == 1
  assert volume.value == 0x1c
  assert configs[0].name == configs[-1].name == 'Global shutdown'
  assert configs[0].value == 0 and configs[-1].value == 1


def test_c3x_keeps_current_speaker_tuning():
  amp = Amplifier()
  amp.set_configs = Mock(return_value=True)
  assert amp.initialize_configuration('tizi')
  configs = amp.set_configs.call_args.args[0]
  assert configs[1:-1] == CONFIG
