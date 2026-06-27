#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B站 UP 主视频 + 动态更新追踪。

设计目标：
- 配置文件驱动，便于长期维护 UP 列表
- 首次运行只建立基线，不制造旧内容通知
- 输出 JSON 报告，方便 OpenClaw cron/后续通知任务读取
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import smtplib
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("缺少依赖 PyYAML，请先运行：pip install -r requirements.txt") from exc

try:
    from bilibili_api import Credential, user
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("缺少依赖 bilibili-api-python，请先运行：pip install -r requirements.txt") from exc

try:
    import aiohttp
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("缺少依赖 aiohttp，请先运行：pip install -r requirements.txt") from exc


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True)
class UpAccount:
    uid: int
    name: str


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"配置文件不存在：{path}\n可先复制：cp config.example.yaml config.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"配置文件格式错误，应为 YAML object：{path}")
    return data


def parse_up_list(raw: Any) -> List[UpAccount]:
    if not isinstance(raw, list):
        raise SystemExit("配置错误：up_list 必须是列表")

    accounts: List[UpAccount] = []
    seen: set[int] = set()
    for idx, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise SystemExit(f"配置错误：up_list 第 {idx} 项必须是 object")
        try:
            uid = int(item["uid"])
        except Exception as exc:
            raise SystemExit(f"配置错误：up_list 第 {idx} 项缺少有效 uid") from exc
        name = str(item.get("name") or uid).strip()
        if uid in seen:
            continue
        seen.add(uid)
        accounts.append(UpAccount(uid=uid, name=name))

    if not accounts:
        raise SystemExit("配置错误：up_list 为空")
    return accounts


def rel_path(config_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": 1, "lastCheck": None, "upData": {}, "stats": {"totalUpdates": 0}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(state, dict):
            state.setdefault("schemaVersion", 1)
            state.setdefault("upData", {})
            state.setdefault("stats", {"totalUpdates": 0})
            return state
    except Exception as exc:
        print(f"⚠️ 读取状态失败，将重建状态：{exc}", file=sys.stderr)
    return {"schemaVersion": 1, "lastCheck": None, "upData": {}, "stats": {"totalUpdates": 0}}


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    rows = list(records)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return "未知"
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def build_credential(cfg: Dict[str, Any]) -> Optional[Credential]:
    bili_cfg = cfg.get("bilibili") or {}
    cred_cfg = bili_cfg.get("credential") or {}
    values = {
        "sessdata": cred_cfg.get("sessdata") or os.environ.get("BILI_SESSDATA"),
        "bili_jct": cred_cfg.get("bili_jct") or os.environ.get("BILI_BILI_JCT"),
        "buvid3": cred_cfg.get("buvid3") or os.environ.get("BILI_BUVID3"),
        "buvid4": cred_cfg.get("buvid4") or os.environ.get("BILI_BUVID4"),
        "dedeuserid": cred_cfg.get("dedeuserid") or os.environ.get("BILI_DEDEUSERID"),
        "proxy": bili_cfg.get("proxy"),
    }
    values = {k: v for k, v in values.items() if v}
    return Credential(**values) if values else None


async def fetch_latest_video(account: UpAccount, credential: Optional[Credential] = None) -> Dict[str, Any]:
    """通过 bilibili-api-python 获取最新公开视频。"""
    try:
        u = user.User(uid=account.uid, credential=credential)
        videos = await u.get_videos(ps=1, pn=1, order=user.VideoOrder.PUBDATE)
        vlist = videos.get("list", {}).get("vlist", [])
        if not vlist:
            return {"kind": "video", "success": True, "item": None}
        latest = vlist[0]
        bvid = latest.get("bvid")
        return {
            "kind": "video",
            "success": True,
            "item": {
                "id": bvid,
                "bvid": bvid,
                "title": latest.get("title") or "未命名视频",
                "created": latest.get("created"),
                "createdText": fmt_ts(latest.get("created")),
                "length": latest.get("length"),
                "play": latest.get("play"),
                "url": f"https://www.bilibili.com/video/{bvid}" if bvid else None,
            },
        }
    except Exception as exc:
        return {"kind": "video", "success": False, "error": str(exc), "item": None}


def _normalize_dynamic_card(card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """兼容 polymer web dynamic feed 的卡片结构。"""
    dyn_id = card.get("id_str") or card.get("id")
    if not dyn_id:
        return None

    modules = card.get("modules") or {}
    module_author = modules.get("module_author") or {}
    module_dynamic = modules.get("module_dynamic") or {}
    major = module_dynamic.get("major") or {}
    desc = module_dynamic.get("desc") or {}
    topic = module_dynamic.get("topic") or {}

    title = None
    url = f"https://t.bilibili.com/{dyn_id}"
    major_type = major.get("type")
    major_archive = major.get("archive") or {}
    major_article = major.get("article") or {}
    major_opus = major.get("opus") or {}

    if major_archive:
        title = major_archive.get("title")
        jump = major_archive.get("jump_url")
        if jump:
            url = jump if str(jump).startswith("http") else f"https:{jump}"
    elif major_article:
        title = major_article.get("title")
        jump = major_article.get("jump_url")
        if jump:
            url = jump if str(jump).startswith("http") else f"https:{jump}"
    elif major_opus:
        title = major_opus.get("title") or major_opus.get("summary", {}).get("text")

    if not title:
        title = desc.get("text") or topic.get("name") or f"动态 {dyn_id}"

    pub_ts = module_author.get("pub_ts") or card.get("pub_ts")
    return {
        "id": str(dyn_id),
        "title": str(title).replace("\n", " ")[:160],
        "type": major_type or card.get("type") or "dynamic",
        "created": pub_ts,
        "createdText": fmt_ts(pub_ts),
        "url": url,
    }


async def fetch_latest_dynamic(
    account: UpAccount,
    session: Optional[aiohttp.ClientSession] = None,
    proxy: Optional[str] = None,
    credential: Optional[Credential] = None,
) -> Dict[str, Any]:
    """获取最新动态。

    优先使用 bilibili-api-python 的 get_dynamics_new()；如果库接口失败，再回退到
    polymer web dynamic HTTP 接口。部分环境访问 HTTP 接口会遇到 412，库接口通常会
    自动补齐签名/headers。
    """
    try:
        u = user.User(uid=account.uid, credential=credential)
        data = await u.get_dynamics_new()
        items = data.get("items") or []
        if not items:
            return {"kind": "dynamic", "success": True, "item": None}
        return {"kind": "dynamic", "success": True, "item": _normalize_dynamic_card(items[0])}
    except Exception as api_exc:
        if session is None:
            return {"kind": "dynamic", "success": False, "error": str(api_exc), "item": None}

        endpoint = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
        params = {
            "host_mid": str(account.uid),
            "features": "itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote,decorationCard",
        }
        try:
            async with session.get(endpoint, params=params, proxy=proxy) as resp:
                text = await resp.text()
                if resp.status != 200:
                    return {
                        "kind": "dynamic",
                        "success": False,
                        "error": f"bilibili-api-python: {api_exc}; HTTP {resp.status}: {text[:200]}",
                        "item": None,
                    }
                payload = json.loads(text)
            if payload.get("code") != 0:
                return {
                    "kind": "dynamic",
                    "success": False,
                    "error": payload.get("message") or payload.get("msg") or str(api_exc),
                    "item": None,
                }
            items = (((payload.get("data") or {}).get("items")) or [])
            if not items:
                return {"kind": "dynamic", "success": True, "item": None}
            return {"kind": "dynamic", "success": True, "item": _normalize_dynamic_card(items[0])}
        except Exception as http_exc:
            return {
                "kind": "dynamic",
                "success": False,
                "error": f"bilibili-api-python: {api_exc}; http fallback: {http_exc}",
                "item": None,
            }


async def fetch_account(
    account: UpAccount,
    cfg: Dict[str, Any],
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
) -> Dict[str, Any]:
    track_cfg = cfg.get("track") or {}
    bili_cfg = cfg.get("bilibili") or {}
    proxy = bili_cfg.get("proxy")
    credential = build_credential(cfg)

    async with sem:
        result: Dict[str, Any] = {"uid": account.uid, "name": account.name, "checks": {}}
        if track_cfg.get("videos", True):
            result["checks"]["video"] = await fetch_latest_video(account, credential=credential)
        if track_cfg.get("dynamics", True):
            result["checks"]["dynamic"] = await fetch_latest_dynamic(account, session=session, proxy=proxy, credential=credential)
        return result


def detect_updates(
    state: Dict[str, Any],
    results: List[Dict[str, Any]],
    first_run_silent: bool,
) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    up_data = state.setdefault("upData", {})
    is_first_run = not bool(up_data)

    for result in results:
        uid = str(result["uid"])
        slot = up_data.setdefault(uid, {"name": result["name"], "video": {}, "dynamic": {}})
        slot["name"] = result["name"]

        for kind, check in (result.get("checks") or {}).items():
            if not check.get("success"):
                continue
            item = check.get("item")
            if not item:
                continue

            kind_state = slot.setdefault(kind, {})
            last_id = kind_state.get("lastId")
            new_id = item.get("id")
            if not new_id:
                continue

            if last_id is None:
                kind_state["lastId"] = new_id
                kind_state["lastTitle"] = item.get("title")
                kind_state["lastSeenAt"] = now_iso()
                continue

            if str(new_id) != str(last_id):
                update = {
                    "detectedAt": now_iso(),
                    "uid": result["uid"],
                    "upName": result["name"],
                    "kind": kind,
                    "item": item,
                    "previous": {
                        "id": last_id,
                        "title": kind_state.get("lastTitle"),
                    },
                }
                # 首次运行且要求静默时，只更新基线，不对外报告更新。
                if not (is_first_run and first_run_silent):
                    updates.append(update)
                kind_state["lastId"] = new_id
                kind_state["lastTitle"] = item.get("title")
                kind_state["lastSeenAt"] = now_iso()

    stats = state.setdefault("stats", {"totalUpdates": 0})
    stats["totalUpdates"] = int(stats.get("totalUpdates") or 0) + len(updates)
    return updates


def print_human_summary(results: List[Dict[str, Any]], updates: List[Dict[str, Any]]) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查完成：{len(results)} 个 UP，发现 {len(updates)} 条更新\n")
    for result in results:
        print(f"👤 {result['name']} ({result['uid']})")
        for kind, check in (result.get("checks") or {}).items():
            label = "视频" if kind == "video" else "动态"
            if not check.get("success"):
                print(f"  ❌ {label}: {check.get('error', '获取失败')}")
                continue
            item = check.get("item")
            if not item:
                print(f"  ⚠️ {label}: 无内容")
                continue
            print(f"  ✅ {label}: {item.get('title')} ({item.get('createdText')})")
    if updates:
        print("\n🎉 新更新：")
        for idx, update in enumerate(updates, 1):
            item = update["item"]
            label = "视频" if update["kind"] == "video" else "动态"
            print(f"  {idx}. 【{update['upName']}】新{label}: {item.get('title')}")
            if item.get("url"):
                print(f"     {item['url']}")
    else:
        print("\n✅ 无需通知的新更新")


def build_email_body(updates: List[Dict[str, Any]], report: Dict[str, Any]) -> str:
    lines = [
        "📺 B站 UP 主更新汇总",
        "=" * 36,
        f"检查时间：{report['checkTime']}",
        f"本次更新：{len(updates)} 条",
        "",
    ]
    for idx, update in enumerate(updates, 1):
        item = update["item"]
        label = "视频" if update["kind"] == "video" else "动态"
        lines.extend([
            f"{idx}. 【{update['upName']}】新{label}",
            f"   标题：{item.get('title')}",
            f"   时间：{item.get('createdText')}",
            f"   链接：{item.get('url')}",
            "",
        ])
    lines.append("🤖 bilibili-up-update-tracker")
    return "\n".join(lines)


def send_email(email_cfg: Dict[str, Any], subject: str, body: str) -> bool:
    if not email_cfg.get("enabled"):
        return False
    required = ["smtp_host", "smtp_port", "smtp_user", "smtp_pass", "to"]
    missing = [k for k in required if not email_cfg.get(k)]
    if missing:
        print(f"⚠️ 邮件配置不完整，跳过发送：{', '.join(missing)}", file=sys.stderr)
        return False

    recipients = email_cfg["to"]
    if isinstance(recipients, str):
        recipients = [recipients]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = email_cfg["smtp_user"]
    msg["To"] = ", ".join(recipients)

    try:
        with smtplib.SMTP(email_cfg["smtp_host"], int(email_cfg["smtp_port"]), timeout=20) as server:
            server.starttls()
            server.login(email_cfg["smtp_user"], email_cfg["smtp_pass"])
            server.sendmail(email_cfg["smtp_user"], recipients, msg.as_string())
        return True
    except Exception as exc:
        print(f"❌ 邮件发送失败：{exc}", file=sys.stderr)
        return False


async def run(config_path: Path, dry_run: bool = False) -> Dict[str, Any]:
    cfg = load_yaml(config_path)
    accounts = parse_up_list(cfg.get("up_list"))
    storage = cfg.get("storage") or {}
    state_file = rel_path(config_path, storage.get("state_file", "data/state.json"))
    latest_report_file = rel_path(config_path, storage.get("latest_report_file", "data/latest-report.json"))
    history_file = rel_path(config_path, storage.get("update_history_file", "data/update-history.jsonl"))
    first_run_silent = bool(cfg.get("first_run_silent", True))

    if dry_run:
        report = {
            "dryRun": True,
            "config": str(config_path),
            "totalUp": len(accounts),
            "upList": [account.__dict__ for account in accounts],
            "stateFile": str(state_file),
            "latestReportFile": str(latest_report_file),
            "historyFile": str(history_file),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report

    timeout_seconds = int((cfg.get("bilibili") or {}).get("timeout_seconds") or 20)
    concurrency = int((cfg.get("bilibili") or {}).get("concurrency") or 4)
    state = load_state(state_file)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"}

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始检查 {len(accounts)} 个 UP 主...")
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        sem = asyncio.Semaphore(max(1, concurrency))
        results = await asyncio.gather(*(fetch_account(account, cfg, session, sem) for account in accounts))

    updates = detect_updates(state, results, first_run_silent=first_run_silent)
    check_time = now_iso()
    state["lastCheck"] = check_time
    save_json(state_file, state)

    report = {
        "schemaVersion": 1,
        "checkTime": check_time,
        "hasUpdate": bool(updates),
        "shouldAlert": bool(updates),
        "updateCount": len(updates),
        "totalUp": len(accounts),
        "updates": updates,
        "results": results,
        "stateFile": str(state_file),
        "historyFile": str(history_file),
    }
    save_json(latest_report_file, report)
    append_jsonl(history_file, updates)

    if updates and (cfg.get("email") or {}).get("enabled"):
        subject = f"🎬 B站 UP 主更新汇总（{len(updates)}条更新）"
        email_sent = send_email(cfg.get("email") or {}, subject, build_email_body(updates, report))
        report["emailSent"] = email_sent
        save_json(latest_report_file, report)

    print_human_summary(results, updates)
    print("\n---RESULT---")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not updates:
        print("\nHEARTBEAT_OK")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="B站 UP 主视频和动态更新追踪")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径，默认 config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="只校验配置，不访问网络、不写状态")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    asyncio.run(run(config_path=config_path, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
