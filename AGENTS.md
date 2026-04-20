# A股交易辅助 Skills

本仓库包含一组 A 股市场分析辅助 Skills，数据源为东方财富 API。

## 环境准备

运行任何 skill 脚本前需安装依赖：

```bash
python3 -m pip install akshare pandas tabulate curl_cffi numpy
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
| a-stock-research-hub | 投研参谋中枢：多维推理分析（环境/题材/风格/持仓/剧本/风险）；短线复盘/scan；波段 swing 参谋 | 复盘、晨报、分析、没时间看盘、两周持有、军师 |
| a-stock-shared | 共享数据模块（被其他 skill 依赖） | 不直接调用 |

## Web 仪表盘

本地运行投研仪表盘：

```bash
python3 -m pip install fastapi uvicorn openai anthropic
python3 web/server.py
# 浏览器打开 http://localhost:8888
```

说明：macOS 上常无 `python` 命令，请统一使用 **`python3`**。Worker 子进程会用当前解释器（`sys.executable`）调用 `hub.py data` 或 **`hub.py data-intel`**（休市时仅刷新情报、不重复拉全市场快照，轮询间隔可在设置里单独调长）。

**交易日历**：Web Worker 用 **上交所交易日**（`akshare.tool_trade_date_hist_sina`，含法定长假与调休上班日），缓存在 `.codex/state/trade_calendar_sse.json`（约 7 天刷新）。可选覆盖文件 `.codex/state/trading_calendar_override.json`：

```json
{
  "force_closed_dates": ["2026-10-02"],
  "force_open_dates": []
}
```

网络与缓存均不可用时，退化为「周一至周五」判断（长假仍可能不准，建议装好 akshare）。

功能：大盘指数、市场广度/情绪、主线题材、选股推荐、AI 深度分析（可配置 LLM 后端）、交易日志。

## 注意事项

- 数据来源为东方财富公开 API，仅供参考，不构成投资建议
- 北向资金实时净买入数据自 2024 年 8 月起停止披露，仅提供持股数据
- 非交易时间段获取的数据为上一交易日收盘数据
