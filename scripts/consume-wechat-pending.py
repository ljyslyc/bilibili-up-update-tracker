#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print and consume one pending WeChat message.

Used by OpenClaw cron announce delivery. Prints NO_REPLY when queue is empty.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "data" / "pending-wechat-message.txt"

if not PENDING.exists():
    print("NO_REPLY")
    raise SystemExit(0)

text = PENDING.read_text(encoding="utf-8").strip()
if not text:
    PENDING.unlink(missing_ok=True)
    print("NO_REPLY")
    raise SystemExit(0)

print(text)
PENDING.unlink(missing_ok=True)
