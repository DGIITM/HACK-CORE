#!/usr/bin/env bash
cd "$(dirname "$0")"
if command -v python3 &>/dev/null; then
    python3 setup_and_run.py
else
    python setup_and_run.py
fi
