#!/bin/zsh
set -e
cd "$(dirname "$0")"
.venv/bin/python -m pytest -q
npm run typecheck --prefix frontend
npm run test --prefix frontend
.venv/bin/python -B scripts/api_setup/check_repository.py
