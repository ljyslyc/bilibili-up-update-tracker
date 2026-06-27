# Bilibili UP Update Tracker

基于 [`Artistkisa/bilibili-up-update-tracker`](https://github.com/Artistkisa/bilibili-up-update-tracker) 思路维护的本地版 B 站 UP 主更新追踪项目。

> 当前基线：2026-06-27 已用示例 UP 主完成一次手动检查，视频/动态接口均可用。

这个版本做了几件事：

- 同时追踪 **视频** 与 **动态** 更新
- 用 `config.yaml` 管理 UP 主列表、状态文件、邮件通知
- 首次运行只建立基线，避免把历史内容全部当作更新
- 输出机器可读的 `data/latest-report.json` 与 `data/update-history.jsonl`
- 可本地手动运行，也可之后接 OpenClaw Gateway cron

> 注意：此前旧的 B 站推送/监控已清理。本项目默认**不会创建 cron、不会推送微信、不会发邮件**；只有你明确要求启用时再配置。

## 目录结构

```text
bilibili-up-update-tracker/
├── config.example.yaml       # 配置模板
├── config.yaml               # 你的实际配置（git 忽略）
├── requirements.txt
├── src/biliup_tracker/
│   ├── __init__.py
│   └── monitor.py            # 主程序
├── scripts/
│   └── run-once.sh           # 手动检查一次
├── data/                     # 状态、报告、历史（git 忽略）
└── logs/                     # 日志（git 忽略）
```

## 快速开始

```bash
cd /Users/holidayyang/.openclaw/workspace/bilibili-up-update-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
python -m biliup_tracker.monitor --config config.yaml
```

或者使用脚本：

```bash
./scripts/run-once.sh
```

## 维护 UP 主列表

编辑 `config.yaml`：

```yaml
up_list:
  - uid: 68559
    name: "22和33"
  - uid: 403748305
    name: "BML制作指挥部"
```

UID 通常来自空间链接：`https://space.bilibili.com/<uid>`。

## 输出说明

- `data/state.json`：每个 UP 主上一次看到的视频/动态 ID
- `data/latest-report.json`：最近一次检查结果
- `data/update-history.jsonl`：每次发现更新时追加一行 JSON

程序结束时会输出 `---RESULT---` 后的 JSON，方便 OpenClaw cron 或其他自动化读取。

## B站风控 / Cookie

如果某个 UP 的视频或动态接口出现 `412`，说明请求被 B 站风控拦了。可以在 `config.yaml` 的 `bilibili.credential` 填入浏览器 Cookie 中的 `SESSDATA`、`bili_jct`、`buvid3` 等字段，或通过环境变量传入：

```bash
export BILI_SESSDATA='...'
export BILI_BILI_JCT='...'
export BILI_BUVID3='...'
```

不建议把真实 Cookie 提交到 git。

## 邮件通知

默认关闭。需要时在 `config.yaml` 中设置：

```yaml
email:
  enabled: true
  smtp_host: "smtp.qq.com"
  smtp_port: 587
  smtp_user: "your_email@qq.com"
  smtp_pass: "your_auth_code"
  to: ["recipient@example.com"]
```

## 之后如果要定时检查

推荐用 OpenClaw Gateway cron，而不是系统 crontab。示例命令由我来加，避免又出现无更新噪音。建议策略：

- 监控任务：`delivery=none`，只写 `latest-report.json`
- 通知任务：只在 `hasUpdate=true` 时 announce

先确认手动运行稳定后再开启。
