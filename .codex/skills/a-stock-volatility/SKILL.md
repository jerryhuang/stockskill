---
name: a-stock-volatility
description: 分析A股市场波动与情绪指标，包括涨跌停统计、连板股梳理、市场情绪温度计、涨停溢价率、市场异动。当用户询问市场情绪、涨跌停数据、连板高度、市场风险、赚钱效应时使用。
---

# A股市场波动与情绪分析

## 依赖

确保已安装: `pip install akshare pandas tabulate`

## 命令

### 涨跌停统计
```bash
python .codex/skills/a-stock-volatility/scripts/volatility.py limit-stats
```

### 涨停股明细
```bash
python .codex/skills/a-stock-volatility/scripts/volatility.py limit-up
```

### 跌停股明细
```bash
python .codex/skills/a-stock-volatility/scripts/volatility.py limit-down
```

### 连板股梳理
```bash
python .codex/skills/a-stock-volatility/scripts/volatility.py streak
```

### 昨日涨停今日表现
```bash
python .codex/skills/a-stock-volatility/scripts/volatility.py premium
```

### 市场情绪综合分析（0-100打分）
```bash
python .codex/skills/a-stock-volatility/scripts/volatility.py sentiment
```

### 市场异动
```bash
python .codex/skills/a-stock-volatility/scripts/volatility.py unusual
```

## 情绪框架

| 分数 | 级别 | 操作建议 |
|------|------|---------|
| 80-100 | 极度亢奋 | 过热，不宜追高 |
| 60-80 | 活跃 | 赚钱效应好，可积极参与 |
| 40-60 | 中性 | 精选个股，适度参与 |
| 20-40 | 低迷 | 轻仓或观望 |
| 0-20 | 冰点 | 关注反转信号 |
