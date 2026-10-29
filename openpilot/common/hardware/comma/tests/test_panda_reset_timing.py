import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call


class TestPandaResetTiming(unittest.TestCase):
  def test_reset_and_recovery_sequences(self):
    # Exercise the actual hardware methods without loading target-only libraries.
    source = Path(__file__).resolve().parents[1] / "hardware.py"
    hardware = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.ClassDef) and n.name == "HardwareComma")
    methods = [n for n in hardware.body if isinstance(n, ast.FunctionDef) and n.name in ("reset_internal_panda", "recover_internal_panda")]
    for model, reset_delay, recovery_delay in [("tici", 1, 0.5), ("three", 1, 0.5), ("tizi", 0.01, 0.01), ("mici", 0.01, 0.01)]:
      for recovery in (False, True):
        with self.subTest(model=model, recovery=recovery):
          events = Mock()
          pins = SimpleNamespace(STM_RST_N=124, STM_BOOT0=134)
          namespace = {"GPIO": pins, "gpio_init": events.init, "gpio_set": events.set, "time": SimpleNamespace(sleep=events.sleep)}
          exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)
          device = SimpleNamespace(get_device_type=lambda: model)
          namespace["recover_internal_panda" if recovery else "reset_internal_panda"](device)
          expected = [call.init(124, True), call.init(134, True), call.set(124, True), call.set(134, recovery),
                      call.sleep(recovery_delay if recovery else reset_delay), call.set(124, False)]
          if recovery:
            expected += [call.sleep(recovery_delay), call.set(134, False)]
          self.assertEqual(events.mock_calls, expected)


if __name__ == "__main__":
  unittest.main()
