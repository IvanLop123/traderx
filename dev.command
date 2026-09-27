#!/bin/zsh
set -e
cd "$(dirname "$0")"
exec .venv/bin/python -B scripts/dev.py
