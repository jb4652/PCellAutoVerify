#!/usr/bin/env sh
set -eu
script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "${PYTHON:-python3}" "$script_directory/run_pcell.py" "$@"
