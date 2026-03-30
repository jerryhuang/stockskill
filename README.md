# A股交易辅助 Skills

一套 Cursor Agent Skills，帮助你在对话中实时获取 A 股市场数据，辅助交易决策。

## 功能模块

| Skill | 功能 |
|-------|------|
| `a-stock-market-overview` | 大盘概览：主要指数、板块涨跌、涨跌家数统计 |
| `a-stock-monitor` | 个股监控：实时行情、技术指标、K线分析 |
| `a-stock-capital-flow` | 资金流向：北向资金、板块资金流、个股主力资金 |
| `a-stock-news` | 消息监控：财经快讯、公司公告、重大政策 |
| `a-stock-volatility` | 市场波动：涨跌停统计、市场情绪、波动率分析 |

## 安装

```bash
pip install -r requirements.txt
```

## 数据来源

所有数据通过 [AKShare](https://github.com/akfamily/akshare) 获取，免费无需 API Key。
