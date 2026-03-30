---
name: a-stock-market-overview
description: 获取A股大盘概览信息，包括主要指数行情、行业板块涨跌排名、市场涨跌家数统计。当用户询问大盘走势、今日行情、市场整体表现、板块轮动时使用。
---

# A股大盘概览

## 功能

提供 A 股市场整体概览：
- 主要指数实时行情（上证、深证、创业板、科创板、北证等）
- 行业板块涨跌排名（申万一级行业）
- 概念板块热度排名
- 全市场涨跌家数统计

## 使用方式

### 获取主要指数行情

```bash
python .cursor/skills/a-stock-market-overview/scripts/market_overview.py index
```

输出：上证指数、深证成指、创业板指、科创50、北证50、沪深300、中证500、中证1000 等指数的最新价、涨跌幅、成交额。

### 获取行业板块排名

```bash
python .cursor/skills/a-stock-market-overview/scripts/market_overview.py sector
```

输出：申万一级行业板块按涨跌幅排名，包含涨跌幅、领涨股。

### 获取概念板块热度

```bash
python .cursor/skills/a-stock-market-overview/scripts/market_overview.py concept
```

输出：当日热门概念板块 Top 20。

### 获取涨跌家数统计

```bash
python .cursor/skills/a-stock-market-overview/scripts/market_overview.py breadth
```

输出：涨停/跌停家数、上涨/下跌/平盘家数。

### 一键获取全部概览

```bash
python .cursor/skills/a-stock-market-overview/scripts/market_overview.py all
```

## 解读指南

- **指数涨跌幅 > 1%**：市场波动较大，关注是否有重大消息驱动
- **涨跌比 > 3:1**：市场强势，赚钱效应好
- **涨跌比 < 1:3**：市场弱势，亏钱效应明显
- **板块集中上涨**：资金抱团，关注主线逻辑
- **板块分化严重**：市场缺乏主线，注意控制仓位
