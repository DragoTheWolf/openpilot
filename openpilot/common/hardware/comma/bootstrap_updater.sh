#!/usr/bin/env bash
set -eu

updater_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -ne 2 ] || [ ! -f "$1" ] || [ ! -f "$2" ]; then
  echo "Usage: $0 AGNOS_PY MANIFEST" >&2
  exit 2
fi

# Magic AGNOS ships a self-contained updater for its own display protocol.
# The old Qt binary cannot use eglfs on Magic (and bypasses its DRM broker).
if systemctl is-active --quiet weston-ready; then
  exec "$updater_dir/updater" "$1" "$2"
elif [ -x /usr/comma/updater ]; then
  exec /usr/comma/updater "$1" "$2"
else
  # Pre-Magic AGNOS uses the original Qt/Wayland updater.
  export QT_QPA_PLATFORM=wayland-egl
  exec "$updater_dir/updater_magic" "$1" "$2"
fi
