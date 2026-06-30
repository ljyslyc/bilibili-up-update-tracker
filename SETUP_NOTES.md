# 部署配置记录

## OpenClaw Gateway Cron 配置

### 1. B站UP视频/动态监控
- **Job ID**: `37f90ac1-1e38-4372-8dba-4df49364a90d`
- **调度**: 每 300 秒（5 分钟）
- **命令**: `./scripts/monitor-to-pending.sh`
- **工作目录**: `bilibili-up-update-tracker/`
- **Payload**: command（不消耗模型 token）
- **Delivery**: none（只写 pending 文件）
- **逻辑**: 检查 UP 主更新，有更新则写入 `data/pending-wechat-message.txt`

### 2. B站UP微信推送队列
- **Job ID**: `f5c42bc2-6619-47e2-b7d4-b63f6a0bc678`
- **调度**: 每 300 秒（5 分钟）
- **命令**: `python3 scripts/consume-wechat-pending.py`
- **工作目录**: `bilibili-up-update-tracker/`
- **Payload**: command（不消耗模型 token）
- **Delivery**: announce → 微信（`openclaw-weixin` / `o9cq801gLLKzAkAbomOgiHcDUQFc@im.wechat`）
- **逻辑**: 读取 pending 文件，有内容则 announce 到微信并清空文件

## 追踪的 UP 主
1. **无敌姜神** (3706959876327428)
2. **文心游龙** (3546942999103780)
3. **一念斩龙** (700502703)

## 追踪内容
- ✅ 视频更新
- ✅ 动态更新

## 注意事项
- `config.yaml` 包含敏感配置（如 Cookie），已被 `.gitignore` 排除
- `data/` 和 `logs/` 目录被 `.gitignore` 排除
- 首次运行 `first_run_silent: true`，只建立基线不通知
- 如需在新机器部署，需要重新配置 `config.yaml` 和 `.venv`
