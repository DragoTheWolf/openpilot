"""Compile comma's unmodified Rebellious Hope ONNX for the stateful runtime.

Temporal sampling follows comma commit 93f5aa4's compile_modeld.py: 20 Hz
queues, 5 Hz context, max-pooled desire pulses, and previous hidden features.
"""
import argparse
import base64
import hashlib
import pickle
from pathlib import Path

import numpy as np
from tinygrad import Tensor, TinyJit, Device, dtypes
from tinygrad.dtype import _to_np_dtype
from tinygrad.nn.onnx import OnnxRunner

MODEL_SHA256 = "433f85f956837606ad1f1cbee4aa7e2158ad23c768dea914b20436c97232741b"
INPUTS = {
  'new_img': ((2, 6, 128, 256), 'uint8'),
  'desire': ((8,), 'float32'),
  'traffic_convention': ((1, 2), 'float32'),
  'action_t': ((1, 2), 'float32'),
  'state_img_q': ((2, 5, 6, 128, 256), 'uint8'),
  'state_desire_q': ((100, 1, 8), 'float32'),
  'state_feat_q': ((96, 1, 512), 'float32'),
}


def legacy_inputs(inputs):
  image_q = inputs['state_img_q'][:, 1:].cat(inputs['new_img'].unsqueeze(1), dim=1)
  desire_q = inputs['state_desire_q'][1:].cat(inputs['desire'].reshape(1, 1, 8), dim=0)
  old_inputs = {
    'img': image_q[0, ::4].reshape(1, 12, 128, 256),
    'big_img': image_q[1, ::4].reshape(1, 12, 128, 256),
    'desire_pulse': desire_q.reshape(25, 4, 1, 8).max(1).reshape(1, 25, 8),
    'features_buffer': inputs['state_feat_q'][::4].reshape(1, 24, 512),
    'traffic_convention': inputs['traffic_convention'],
    'action_t': inputs['action_t'],
  }
  return old_inputs, image_q, desire_q


def compile_model(path, output, benchmark_runs):
  from examples.openpilot.compile_onnx import onnx_metadata
  from examples.openpilot.helpers import allocate_inputs, dump_pickle, benchmark, load_pickle
  assert hashlib.sha256(path.read_bytes()).hexdigest() == MODEL_SHA256, 'Unexpected Rebellious Hope artifact'
  runner = OnnxRunner(path)
  metadata, output_shapes = onnx_metadata(path)
  slices = pickle.loads(base64.b64decode(metadata['output_slices']))
  specs = {name: (shape, dtype, Device.DEFAULT) for name, (shape, dtype) in INPUTS.items()}

  def wrapped(inputs):
    old_inputs, image_q, desire_q = legacy_inputs(inputs)
    model_output = runner({k: v.cast(runner.graph_inputs[k].dtype) for k, v in old_inputs.items()})['outputs'].cast(dtypes.float32)
    feature = model_output[:, slices['hidden_state']].reshape(1, 1, 512)
    return {'outputs': model_output, 'next_state_img_q': image_q, 'next_state_desire_q': desire_q,
            'next_state_feat_q': inputs['state_feat_q'][1:].cat(feature, dim=0)}

  dummy = allocate_inputs(specs)
  output_specs = {k: (v.shape, np.dtype(_to_np_dtype(v.dtype)).name, Device.DEFAULT) for k, v in wrapped(dummy).items()}

  def make_inputs(seed):
    rng = np.random.default_rng(seed)

    def initialize(arrays):
      for value in arrays.values():
        value[:] = rng.integers(0, 256, value.shape, dtype=np.uint8) if value.dtype == np.uint8 else rng.standard_normal(value.shape)

    return allocate_inputs(specs, initialize) | {'output_buffers': allocate_inputs(output_specs)}

  @TinyJit(prune=True)
  def run(output_buffers, **inputs):
    outputs = wrapped(inputs)
    Tensor.realize(*(output_buffers[k].assign(v) for k, v in outputs.items()))

  inputs = make_inputs(42)
  expected = benchmark(run, **inputs)
  for _ in range(2):
    np.testing.assert_equal(benchmark(run, **inputs), expected)
  with np.testing.assert_raises(AssertionError):
    np.testing.assert_equal(benchmark(run, **make_inputs(43)), expected)
  for _ in range(benchmark_runs):
    np.testing.assert_equal(benchmark(run, **inputs), expected)
  artifact = {
    'metadata': {'metadata': metadata, 'input_shapes': {k: v[0] for k, v in specs.items()},
                 'output_shapes': output_shapes | {k: v[0] for k, v in output_specs.items()},
                 'source_commit': '93f5aa469a72b7621aef7da7901c100e0113e4d9', 'source_sha256': MODEL_SHA256},
    'run': run, 'input_specs': specs, 'output_specs': output_specs,
  }
  dump_pickle(artifact, output)
  loaded = load_pickle(output, out_of_band=True)
  np.testing.assert_equal(benchmark(loaded['run'], **make_inputs(42)), expected)
  print(f'Rebellious Hope compiled and serialization verified: {output}')


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('onnx', type=Path)
  parser.add_argument('output', type=Path)
  parser.add_argument('--benchmark-runs', type=int, default=1)
  parser.add_argument('--out-of-band', action='store_true')
  args = parser.parse_args()
  compile_model(args.onnx, args.output, args.benchmark_runs)
