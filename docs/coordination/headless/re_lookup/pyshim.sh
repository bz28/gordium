#!/bin/sh
# the lookup subprocess, with the R-2a stand-in (see lookup_shim.py); the venv python is the cloud one
exec "${GORDIUM_PYTHON:-/home/user/venv/bin/python}" "$(dirname "$0")/lookup_shim.py" "$@"
