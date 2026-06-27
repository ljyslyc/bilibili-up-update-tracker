#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read latest-report.json and write pending-wechat-message.txt only when updates exist."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data" / "latest-report.json"
PENDING = ROOT / "data" / "pending-wechat-message.txt"


def kind_label(kind: str) -> str:
    return "视频" if kind == "video" else "动态" if kind == "dynamic" else kind


def main() -> None:
    if not REPORT.exists():
        if PENDING.exists():
            PENDING.unlink()
        print("NO_REPLY")
        return

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    updates = report.get("updates") or []
    if not updates:
        if PENDING.exists():
            PENDING.unlink()
        print("NO_REPLY")
        return

    lines = ["🔔 B站 UP 更新提醒", f"检查时间：{report.get('checkTime', '')}", ""]
    for idx, update in enumerate(updates, 1):
        item = update.get("item") or {}
        label = kind_label(update.get("kind", ""))
        lines.extend(
            [
                f"{idx}. 【{update.get('upName', update.get('uid'))}】新{label}",
                f"标题：{item.get('title', '')}",
                f"时间：{item.get('createdText', '')}",
                f"链接：{item.get('url', '')}",
                "",
            ]
        )

    text = "\n".join(lines).strip() + "\n"
    PENDING.write_text(text, encoding="utf-8")
    print(f"PENDING_WRITTEN {PENDING}")


if __name__ == "__main__":
    main()
