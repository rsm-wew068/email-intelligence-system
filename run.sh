#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
PORT="${1:-8080}"
exec /opt/homebrew/Caskroom/miniconda/base/bin/python3 run.py "$PORT"
