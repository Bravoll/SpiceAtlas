#!/usr/bin/env bash
set -eu
updater_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ "$#" -gt 0 ]; then
  exec python3 "$updater_root/update.py" --target "$1" --restart
else
  exec python3 "$updater_root/update.py" --restart
fi
