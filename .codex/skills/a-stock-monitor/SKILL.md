---
name: a-stock-monitor
description: 监控A股个股行情，获取实时报价、K线数据、技术指标分析（MA/MACD/KDJ/RSI/BOLL）。当用户询问某只股票的价格、走势、技术面分析、买卖信号、K线时使用。
---

# A股个股监控

## 依赖

确保已安装: `pip install akshare pandas tabulate`

## 命令

### 查询个股实时行情
```bash
python .codex/skills/a-stock-monitor/scripts/stock_monitor.py quote 600519
python .codex/skills/a-stock-monitor/scripts/stock_monitor.py quote 600519,000858,300750
```

### 获取K线数据
```bash
python .codex/skills/a-stock-monitor/scripts/stock_monitor.py kline 600519 daily 60
```
参数：股票代码、周期（daily/weekly/monthly）、天数。

### 技术指标分析
```bash
python .codex/skills/a-stock-monitor/scripts/stock_monitor.py tech 600519
```
输出 MA、MACD、KDJ、RSI、BOLL 指标及信号。

### 搜索股票
```bash
python .codex/skills/a-stock-monitor/scripts/stock_monitor.py search 贵州茅台
```

## 信号参考

| 指标 | 买入信号 | 卖出信号 |
|------|---------|---------|
| MACD | DIF上穿DEA（金叉） | DIF下穿DEA（死叉） |
| KDJ | K上穿D且J<20 | K下穿D且J>80 |
| RSI | RSI<30（超卖） | RSI>70（超买） |
| BOLL | 价格触及下轨 | 价格触及上轨 |
