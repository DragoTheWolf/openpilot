from opendbc.car.volkswagen.values import CAR, VolkswagenFlags, VolkswagenSafetyFlags

PATCHED_EPS_PARAM = "VwPqEpsPatched"
AOL_PARAM = "VwPqAol"
AOL_DESCRIPTION = (
  "Flip cruise main on to engage steering, or use factory cruise/SET/RES. Braking cancels factory speed control but keeps AOL steering active. " +
  "SET/RES can engage steering with cruise main on; Cancel or main off disengages it. " +
  "Factory cruise alone controls speed. Change while parked, then reboot."
)
PATCHED_EPS_DESCRIPTION = (
  "Enable only for a Golf PQ with EPS firmware patched for low-speed steering. " +
  "Sets the steering minimum to 0 instead of 31 mph (50 km/h). " +
  "Factory cruise must still be engaged. Change while parked, then reboot to apply."
)


def set_patched_pq_eps(params, enabled):
  params.put_bool(PATCHED_EPS_PARAM, enabled, block=True)
  params.remove("CarParamsCache")


def apply_patched_pq_eps(cp, params):
  # IQ release's VwPqEpsPatched option sets minSteerSpeed to zero. Apply it
  # only to this port's detected NMS CC-only configuration, without importing
  # a Params dependency into opendbc or altering cruise/safety permissions.
  if (params.get_bool(PATCHED_EPS_PARAM) and cp.brand == 'volkswagen' and
      cp.carFingerprint == CAR.VOLKSWAGEN_PASSAT_NMS and cp.flags & VolkswagenFlags.PQ and
      cp.flags & VolkswagenFlags.PQ_CC_ONLY and cp.pcmCruise and not cp.openpilotLongitudinalControl):
    cp.minSteerSpeed = 0.


def pq_aol_enabled(cp):
  return (cp.brand == 'volkswagen' and cp.carFingerprint == CAR.VOLKSWAGEN_PASSAT_NMS and
          bool(cp.flags & VolkswagenFlags.PQ) and bool(cp.flags & VolkswagenFlags.PQ_CC_ONLY) and bool(cp.flags & VolkswagenFlags.PQ_AOL) and
          cp.pcmCruise and not cp.openpilotLongitudinalControl)


def set_pq_aol(params, enabled):
  params.put_bool(AOL_PARAM, enabled, block=True)
  params.remove("CarParamsCache")


def apply_pq_aol(cp, params):
  if (params.get_bool(AOL_PARAM) and cp.brand == 'volkswagen' and cp.carFingerprint == CAR.VOLKSWAGEN_PASSAT_NMS and
      cp.flags & VolkswagenFlags.PQ and cp.flags & VolkswagenFlags.PQ_CC_ONLY and cp.pcmCruise and not cp.openpilotLongitudinalControl):
    cp.flags |= VolkswagenFlags.PQ_AOL.value
    cp.safetyConfigs[-1].safetyParam |= VolkswagenSafetyFlags.PQ_AOL.value
