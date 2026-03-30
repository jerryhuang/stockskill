---
name: a-stock-market-overview
description: 获取A股大盘概览信息，包括主要指数行情（上证、深证、创业板、科创50、沪深300等）、行业板块涨跌排名、概念板块热度、全市场涨跌家数统计。当用户询问大盘走势、今日行情、市场整体表现、板块轮动、涨跌统计时使用。
---

# A股大盘概览

## 依赖

确保已安装: `pip install akshare pandas tabulate`

## 命令

### 主要指数行情
```bash
python .codex/skills/a-stock-market-overview/scripts/market_overview.py index
```

### 行业板块排名
```bash
python .codex/skills/a-stock-market-overview/scripts/market_overview.py sector
```

### 概念板块热度 Top 20
```bash
python .codex/skills/a-stock-market-overview/scripts/market_overview.py concept
```

### 涨跌家数统计
```bash
python .codex/skills/a-stock-market-overview/scripts/market_overview.py breadth
```

### 一键全部
```bash
python .codex/skills/a-stock-market-overview/scripts/market_overview.py all
```

## 解读指南

- 涨跌比 > 3:1 → 市场强势；< 1:3 → 市场弱势
- 板块集中上涨 → 资金抱团主线；分化严重 → 缺乏主线
- 涨停数 > 80 → 赚钱效应好；< 30 → 市场低迷
