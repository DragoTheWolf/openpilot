#!/usr/bin/env bash
set -eu

updater_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -ne 2 ] || [ ! -f "$1" ] || [ ! -f "$2" ]; then
  echo "Usage: $0 AGNOS_PY MANIFEST" >&2
  exit 2
fi

# Old AGNOS uses Qt/Magic directly on the display. Its installed Python UI
# dependencies cannot run the current Weston updater before the OS upgrade.
if systemctl is-active --quiet weston-ready; then
  exec "$updater_dir/updater" "$1" "$2"
else
  export QT_QPA_PLATFORM=eglfs
  exec "$updater_dir/updater_magic" "$1" "$2"
fi
