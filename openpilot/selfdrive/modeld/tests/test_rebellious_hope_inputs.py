import numpy as np
from tinygrad import Tensor

from openpilot.selfdrive.modeld.compile_rebellious_hope import legacy_inputs, INPUTS


def test_original_comma_temporal_sampling():
  arrays = {key: np.zeros(shape, dtype=dtype) for key, (shape, dtype) in INPUTS.items()}
  for frame in range(5):
    arrays['state_img_q'][:, frame] = frame
  arrays['new_img'][:] = 5
  for frame in range(100):
    arrays['state_desire_q'][frame] = frame
  arrays['desire'][:] = 100
  for frame in range(96):
    arrays['state_feat_q'][frame] = frame
  old, image_q, desire_q = legacy_inputs({key: Tensor(value, device='CPU:LLVM') for key, value in arrays.items()})
  np.testing.assert_array_equal(old['img'].numpy()[0, :, 0, 0], [1] * 6 + [5] * 6)
  np.testing.assert_array_equal(old['big_img'].numpy()[0, :, 0, 0], [1] * 6 + [5] * 6)
  np.testing.assert_array_equal(old['desire_pulse'].numpy()[0, :, 0], np.arange(4, 101, 4))
  np.testing.assert_array_equal(old['features_buffer'].numpy()[0, :, 0], np.arange(0, 96, 4))
  np.testing.assert_array_equal(image_q.numpy()[0, :, 0, 0, 0], [1, 2, 3, 4, 5])
  np.testing.assert_array_equal(desire_q.numpy()[:, 0, 0], np.arange(1, 101))
