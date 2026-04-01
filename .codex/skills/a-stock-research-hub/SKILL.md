---
name: a-stock-research-hub
description: A股投研编排中枢。短线：晨报、盘中 scan（新闻/公告关键词+情绪）、收盘复盘；波段（约两周少看盘）：swing 参谋简报（指数环境+自选 MA 位）。当用户问「今天怎么做、复盘、晨报、波段持有两周、没时间看盘、军师参谋」或要结构化风控清单时使用。
---

# A股龙虾投研中枢

## 依赖

仓库根目录已提供 `.codex/setup.sh` 自动安装依赖。手动安装：

```bash
pip install akshare pandas tabulate curl_cffi numpy
```

## 命令

### 短线 · 晨报（开盘前）

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py morning
```

### 短线 · 盘中预警（事件扫描，含快讯/公告关键词）

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py scan
```

### 短线 · 收盘复盘

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py close
```

### 晚间参谋简报（适合定时任务）

适合云端每天晚上自动跑，输出：环境、主线、自选/持仓体检、明日动作，并保存到 `.codex/state/reports/`。

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py nightly
```

### 波段（约两周，少看盘）· 参谋简报

适合**已选好标的、持有约 10 个交易日**、每周只看 1～2 次盘面的用法：

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py swing
```

输出包含：节奏建议、指数环境、上证近段走势、自选相对 MA20 与近 5 日涨跌幅（**不构成荐股**，仅技术位体检）。

波段参数可在 `.codex/state/config.json` 的 `swing` 段调整：`hold_days_target`、`review_per_week`、`ma_window`、`watchlist_snapshot_max`。

### 管理自选与关键词

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist show
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist template
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist add-stock 600519
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist set-field 600519 thesis 两周波段逻辑
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist set-field 600519 stop_loss 1400
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist add-keyword 回购
```

## 输出规范（固定四段，晨报/复盘）

- **TL;DR**：一句话结论（进攻/防守/混沌或波段环境）
- **证据**：数据点
- **行动**：观察/试错/减仓/回避
- **风险**：失效条件

## 注意事项

- 数据来自公开接口，仅供参考，**不构成投资建议**
- 全市场快照偶发失败时，部分广度指标会降级或跳过
