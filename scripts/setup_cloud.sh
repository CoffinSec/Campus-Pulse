#!/usr/bin/env bash
# Reproduce the tested Python environment; never download a model automatically.
set -euo pipefail
cd /workspace/Campus-Pulse
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
export PIP_CACHE_DIR=/workspace/.cache/campuspulse-pip
.venv/bin/python -m pip install --disable-pip-version-check -r requirements-lock.txt
.venv/bin/python -m pip check
.venv/bin/python -m scripts.smoke_test
