---
name: a-stock-volatility
description: 分析A股市场波动与情绪指标，包括涨跌停统计、连板股梳理、市场情绪温度计、波动率分析。当用户询问市场情绪、涨跌停数据、连板高度、市场风险、赚钱效应时使用。
---

# A股市场波动与情绪分析

## 功能

- 涨跌停统计与明细
- 连板股梳理（连板高度/接力情绪）
- 市场情绪温度计（综合多维度指标）
- 昨日涨停今日表现（涨停溢价率）
- 市场异动个股（急涨/急跌/大单）

## 使用方式

### 涨跌停统计

```bash
python .cursor/skills/a-stock-volatility/scripts/volatility.py limit-stats
```

输出：涨停/跌停家数、炸板率、涨停封板金额等。

### 涨停股明细

```bash
python .cursor/skills/a-stock-volatility/scripts/volatility.py limit-up
```

输出：今日涨停股列表，含连板天数、封板时间、所属板块。

### 跌停股明细

```bash
python .cursor/skills/a-stock-volatility/scripts/volatility.py limit-down
```

### 连板股梳理

```bash
python .cursor/skills/a-stock-volatility/scripts/volatility.py streak
```

输出：按连板天数排序的涨停股，帮助判断市场高度和情绪。

### 昨日涨停今日表现

```bash
python .cursor/skills/a-stock-volatility/scripts/volatility.py premium
```

输出：昨日涨停股今日的涨跌幅，计算涨停溢价率。

### 市场情绪综合分析

```bash
python .cursor/skills/a-stock-volatility/scripts/volatility.py sentiment
```

综合涨跌比、涨跌停比、连板高度、炸板率等给出情绪打分。

### 市场异动股

```bash
python .cursor/skills/a-stock-volatility/scripts/volatility.py unusual
```

## 情绪判断框架

| 指标 | 冰点 | 低迷 | 中性 | 活跃 | 亢奋 |
|------|------|------|------|------|------|
| 涨跌比 | <1:3 | 1:3~1:1 | 1:1~2:1 | 2:1~3:1 | >3:1 |
| 涨停数 | <30 | 30~50 | 50~80 | 80~120 | >120 |
| 跌停数 | >30 | 15~30 | 5~15 | 2~5 | <2 |
| 连板高度 | 2板 | 3板 | 4~5板 | 6~7板 | >8板 |
| 炸板率 | >50% | 35~50% | 20~35% | 10~20% | <10% |

- **冰点/低迷**：适合观望或轻仓试探
- **中性**：正常交易，控制仓位
- **活跃**：赚钱效应好，可适当加仓
- **亢奋**：注意风险，可能接近阶段性高点
