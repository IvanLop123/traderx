#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Local Python environment missing. Follow docs/API_SETUP.md to install it.'
  exit 2
fi
exec .venv/bin/python -B scripts/api_setup/check_environment.py
