# A股交易辅助 Skills

本仓库包含一组 A 股市场分析辅助 Skills，数据源为东方财富 API。

## 环境准备

运行任何 skill 脚本前需安装依赖：

```bash
pip install akshare pandas tabulate curl_cffi numpy
```

或者 `.codex/setup.sh` 会自动完成安装。

## 可用 Skills

| Skill | 功能 | 触发关键词 |
|-------|------|-----------|
| a-stock-market-overview | 大盘指数、板块行情、涨跌统计 | 大盘、行情、指数、板块 |
| a-stock-monitor | 个股实时行情、K线、技术指标 | 股票行情、K线、MACD、技术分析 |
| a-stock-capital-flow | 资金流向、北向资金、板块资金 | 资金流向、主力、北向资金 |
| a-stock-news | 财经快讯、公告、新闻日历 | 新闻、快讯、公告、财经日历 |
| a-stock-volatility | 涨跌停统计、市场情绪、异动 | 涨停、跌停、炸板、情绪、异动 |
| a-stock-shared | 共享数据模块（被其他 skill 依赖） | 不直接调用 |

## 注意事项

- 数据来源为东方财富公开 API，仅供参考，不构成投资建议
- 北向资金实时净买入数据自 2024 年 8 月起停止披露，仅提供持股数据
- 非交易时间段获取的数据为上一交易日收盘数据
