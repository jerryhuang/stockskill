---
name: a-stock-news
description: 获取A股市场财经新闻、公司公告、重大政策动态。当用户询问最新财经消息、某只股票的公告、市场重大新闻、政策变化、新闻联播内容时使用。
---

# A股消息监控

## 依赖

确保已安装: `pip install akshare pandas tabulate`

## 命令

### 最新财经快讯
```bash
python .codex/skills/a-stock-news/scripts/news_monitor.py flash 30
```

### 个股公告
```bash
python .codex/skills/a-stock-news/scripts/news_monitor.py announce 600519 10
```

### 个股相关新闻
```bash
python .codex/skills/a-stock-news/scripts/news_monitor.py stock-news 600519
```

### 新闻联播文字稿
```bash
python .codex/skills/a-stock-news/scripts/news_monitor.py cctv 20260328
```

### 财经日历
```bash
python .codex/skills/a-stock-news/scripts/news_monitor.py calendar
```

## 解读

- 新闻联播提及某行业 → 次日该板块大概率有表现
- 业绩超预期 → 短期涨幅；低于预期 → 补跌
- 大股东减持 → 负面；回购/增持 → 正面
