#!/usr/bin/env bash

# Original comma 3 has removable NVMe storage. Later devices use internal UFS.
# AGNOS versions that no longer mount NVMe need this before loggerd starts.
mount_c3_storage() {
  local model_path=/sys/firmware/devicetree/base/model
  [ -r "$model_path" ] && grep -q tici "$model_path" || return 0
  local attempt
  for attempt in {1..10}; do
    [ -b /dev/nvme0n1p1 ] && break
    sleep 1
  done
  [ -b /dev/nvme0n1p1 ] || return 0
  local target=/data/media/0/realdata
  if ! mountpoint -q "$target"; then
    mkdir -p "$target"
    if ! sudo mount /dev/nvme0n1p1 "$target"; then
      echo "Could not mount C3 NVMe storage" >&2
      return 1
    fi
  fi
}
