#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/init_env.py
.venv/bin/python manage.py migrate
.venv/bin/python manage.py check_setup
printf '%s\n' 'Ready. Start with .venv/bin/python manage.py runserver'
