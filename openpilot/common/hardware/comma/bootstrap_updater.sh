#!/usr/bin/env bash
set -eu

updater_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -ne 2 ] || [ ! -f "$1" ] || [ ! -f "$2" ]; then
  echo "Usage: $0 AGNOS_PY MANIFEST" >&2
  exit 2
fi

# Stock AGNOS 12.8 uses Weston. The current updater targets Magic, so use
# comma's official v0.10.0 Weston artifact before upgrading that stock OS.
if systemctl is-active --quiet weston-ready; then
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/var/tmp/weston}"
  export QT_QPA_PLATFORM=wayland-egl
  exec "$updater_dir/updater_weston" "$1" "$2"
elif [ -x /usr/comma/updater ]; then
  # Magic AGNOS supplies an updater for its own display protocol.
  exec /usr/comma/updater "$1" "$2"
else
  # Pre-Magic AGNOS uses the original Qt/Wayland updater.
  export QT_QPA_PLATFORM=wayland-egl
  exec "$updater_dir/updater_magic" "$1" "$2"
fi
