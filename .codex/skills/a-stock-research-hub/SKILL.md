---
name: a-stock-research-hub
description: 面向短线交易的A股投研编排中枢。会综合指数/广度/涨跌停/连板/新闻公告与自选股，生成晨报、盘中预警、收盘复盘，并给出明确可执行的观察清单与风控失效条件。当用户问“今天怎么做、盘中异动、复盘、晨报、自选股是否触发信号、题材主线/退潮”等时使用。
---

# A股龙虾投研中枢（短线）

## 依赖

仓库根目录已提供 `.codex/setup.sh` 自动安装依赖。手动安装：

```bash
pip install akshare pandas tabulate curl_cffi numpy
```

## 命令

### 晨报（开盘前）

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py morning
```

### 盘中预警（事件扫描）

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py scan
```

### 收盘复盘（收盘后）

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py close
```

### 管理自选与关键词

```bash
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist show
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist add-stock 600519
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist add-keyword 回购
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist rm-stock 600519
python .codex/skills/a-stock-research-hub/scripts/hub.py watchlist rm-keyword 回购
```

## 输出规范（固定四段）
- **TL;DR**：一句话给结论（进攻/防守/混沌）\n
- **证据**：触发阈值的数据点\n
- **行动**：明确到“仓位/观察/试错/回避”\n
- **风险**：失效条件（例如跌停扩张、连板断板、广度转弱）\n

