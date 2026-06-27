#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
"$PY" -m biliup_tracker.monitor --config "$ROOT/config.yaml" > "$ROOT/logs/last-monitor.log" 2>&1
"$PY" "$ROOT/scripts/build-wechat-pending.py"
