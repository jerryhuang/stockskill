---
name: a-stock-news
description: 获取A股市场财经新闻、公司公告、重大政策动态。当用户询问最新财经消息、某只股票的公告、市场重大新闻、政策变化时使用。
---

# A股消息监控

## 功能

- 财经快讯（东方财富实时快讯）
- 个股公告查询
- 重大财经新闻
- 个股相关新闻
- CCTV 新闻联播摘要（政策风向）

## 使用方式

### 获取最新财经快讯

```bash
python .cursor/skills/a-stock-news/scripts/news_monitor.py flash 30
```

输出最近 N 条财经快讯（默认30条）。

### 查询个股公告

```bash
python .cursor/skills/a-stock-news/scripts/news_monitor.py announce 600519 10
```

输出指定股票最近 N 条公告标题和日期。

### 获取个股相关新闻

```bash
python .cursor/skills/a-stock-news/scripts/news_monitor.py stock-news 600519
```

### 获取 CCTV 新闻联播文字稿

```bash
python .cursor/skills/a-stock-news/scripts/news_monitor.py cctv 20260328
```

输出指定日期的新闻联播摘要，可用于解读政策风向。

### 获取全球财经日历

```bash
python .cursor/skills/a-stock-news/scripts/news_monitor.py calendar
```

## 解读指南

- **政策利好**：关注受益板块，通常有1-3天的炒作窗口
- **业绩公告**：超预期利好可能带来短期涨幅；低于预期可能补跌
- **增减持公告**：大股东/高管减持是负面信号，增持是正面信号
- **定增/回购**：回购通常是利好，定增需看价格和用途
- **新闻联播提及某行业**：次日该板块大概率有表现
