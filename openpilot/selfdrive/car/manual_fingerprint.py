import os
from contextlib import contextmanager

from opendbc.car.volkswagen.values import CAR

MANUAL_CAR_PARAM = "ManualCarFingerprint"
MANUAL_CAR_OPTIONS = ("", str(CAR.VOLKSWAGEN_PASSAT_NMS))
MANUAL_CAR_LABELS = ("Automatic", "Passat NMS")
MANUAL_CAR_DESCRIPTION = (
  "Select Passat NMS for this Golf PQ if automatic detection does not recognize the car. " +
  "Factory cruise controls speed. Change only while parked, then reboot to apply."
)


def manual_car_index(params):
  selection = params.get(MANUAL_CAR_PARAM, return_default=True)
  return MANUAL_CAR_OPTIONS.index(selection) if selection in MANUAL_CAR_OPTIONS else 0


def set_manual_car(params, index):
  if index not in range(len(MANUAL_CAR_OPTIONS)):
    raise ValueError(f"Invalid manual car index: {index}")
  # Use an explicit sentinel because Params treats an empty string as absent.
  params.put(MANUAL_CAR_PARAM, MANUAL_CAR_OPTIONS[index] or "AUTO", block=True)
  params.remove("CarParamsCache")


@contextmanager
def manual_fingerprint(params):
  selection = MANUAL_CAR_OPTIONS[manual_car_index(params)]
  if not selection:
    yield
    return

  # Keep CAN collection for topology/configuration checks, but do not depend on
  # VIN/FW identification for an explicitly selected model. Limit to this port.
  keys = ("FINGERPRINT", "SKIP_FW_QUERY")
  previous = {key: os.environ.get(key) for key in keys}
  os.environ["FINGERPRINT"] = selection
  os.environ["SKIP_FW_QUERY"] = "1"
  try:
    yield
  finally:
    for key, value in previous.items():
      if value is None:
        os.environ.pop(key, None)
      else:
        os.environ[key] = value
