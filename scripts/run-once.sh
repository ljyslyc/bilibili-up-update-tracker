#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f config.yaml ]]; then
  cp config.example.yaml config.yaml
  echo "已从 config.example.yaml 创建 config.yaml；请按需编辑 UP 主列表。" >&2
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m biliup_tracker.monitor --config config.yaml "$@"
