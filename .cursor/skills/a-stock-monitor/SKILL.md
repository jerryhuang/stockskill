---
name: a-stock-monitor
description: 监控A股个股行情，获取实时报价、K线数据、技术指标分析。当用户询问某只股票的价格、走势、技术面分析、买卖信号时使用。
---

# A股个股监控

## 功能

- 个股实时报价（价格、涨跌、成交量、换手率）
- 日K/周K/月K 历史数据
- 技术指标计算（MA、MACD、KDJ、RSI、BOLL）
- 多股票批量监控
- 股票搜索（按名称或代码）

## 使用方式

### 查询个股实时行情

```bash
python .cursor/skills/a-stock-monitor/scripts/stock_monitor.py quote 600519
```

支持 6 位代码（如 600519）或带前缀代码（如 sh600519）。

### 查询多只股票

```bash
python .cursor/skills/a-stock-monitor/scripts/stock_monitor.py quote 600519,000858,300750
```

### 获取 K 线数据

```bash
python .cursor/skills/a-stock-monitor/scripts/stock_monitor.py kline 600519 daily 60
```

参数：股票代码、周期（daily/weekly/monthly）、天数（默认60）。

### 技术指标分析

```bash
python .cursor/skills/a-stock-monitor/scripts/stock_monitor.py tech 600519
```

输出 MA、MACD、KDJ、RSI、BOLL 等指标及买卖信号判断。

### 搜索股票

```bash
python .cursor/skills/a-stock-monitor/scripts/stock_monitor.py search 贵州茅台
```

## 技术指标解读

| 指标 | 买入信号 | 卖出信号 |
|------|---------|---------|
| MACD | DIF上穿DEA（金叉） | DIF下穿DEA（死叉） |
| KDJ | K上穿D且J<20（超卖金叉） | K下穿D且J>80（超买死叉） |
| RSI | RSI<30（超卖） | RSI>70（超买） |
| BOLL | 价格触及下轨 | 价格触及上轨 |
| MA | 短期均线上穿长期均线 | 短期均线下穿长期均线 |
