# A 股交易辅助 · Skills & 投研仪表盘

面向 **Cursor Agent** 与本地脚本的一套 A 股数据与投研工具：在对话中拉行情/资金/新闻，或通过 **Web 仪表盘** 定时采集、情报分析与 AI 报告。数据以 **东方财富公开接口** 为主（`a-stock-shared` 限速与缓存），部分能力辅以 AkShare。

> **免责声明**：仅供学习与研究，不构成投资建议。

---

## 功能概览

### Cursor Skills（对话触发）

| Skill | 路径（`.codex/skills/`） | 能力摘要 |
|-------|-------------------------|----------|
| **a-stock-market-overview** | `a-stock-market-overview` | 主要指数、板块涨跌、涨跌家数 |
| **a-stock-monitor** | `a-stock-monitor` | 个股报价、K 线、常用技术指标 |
| **a-stock-capital-flow** | `a-stock-capital-flow` | 北向持股、板块/个股资金流（注：成交净买额已停更） |
| **a-stock-news** | `a-stock-news` | 快讯、公告、财经日历等 |
| **a-stock-volatility** | `a-stock-volatility` | 涨跌停、连板、情绪与异动 |
| **a-stock-research-hub** | `a-stock-research-hub` | 投研中枢：环境/题材/选股/交易日志/复盘与波段简报 |
| **a-stock-shared** | `a-stock-shared` | 共享拉数模块（一般不单独使用） |

更细的触发词与工作流程见 **[AGENTS.md](./AGENTS.md)**（给 Agent 的规则说明，也可作人读索引）。

### 投研中枢 CLI（`hub.py`）

在仓库根目录执行（**macOS 请用 `python3`**）：

```bash
python3 .codex/skills/a-stock-research-hub/scripts/hub.py data          # 全量 JSON：指数、广度、题材、自选、选股、情报 intel 等
python3 .codex/skills/a-stock-research-hub/scripts/hub.py data-intel    # 仅刷新情报（合并上一轮行情缓存，休市轮询用）
python3 .codex/skills/a-stock-research-hub/scripts/hub.py screen        # 选股候选列表
python3 .codex/skills/a-stock-research-hub/scripts/hub.py weekprob 600519  # 单票约 5 日收涨概率（启发式）
python3 .codex/skills/a-stock-research-hub/scripts/hub.py doctor        # 环境自检（东财 K 线、快照、链路）
python3 .codex/skills/a-stock-research-hub/scripts/hub.py trade stats   # 交易日志胜率统计（若已记账）
```

自选、关键词、交易记录等状态默认在 **`.codex/state/`** 下（详见各 Skill 文档）。

### Web 投研仪表盘

后台 **Worker** 按 **上交所交易日历** 与时段切换策略：

- **连续竞价**：定时执行 `hub.py data`（全市场行情 + 情报 + 可选 AI 报告）。
- **休市 / 盘后**：执行 `hub.py data-intel`，**不重复拉全市场快照**，仅刷新情报；轮询间隔可在页面单独拉长。

启动方式：

```bash
python3 -m pip install -r requirements.txt
# 若 Skills 脚本报缺依赖，可补：python3 -m pip install curl_cffi numpy
python3 web/server.py
```

浏览器访问：**http://localhost:8888**  
在「系统设置」中配置 LLM（OpenAI 兼容或 Anthropic 兼容）、Worker 间隔与 **休市情报间隔**。API Key 可写入本地密钥文件（见启动日志中的路径）。

**交易日历**：`web/cn_calendar.py` 使用 AkShare 上交所交易日数据并本地缓存；可选 **`.codex/state/trading_calendar_override.json`** 强制休市/开市日，详见 AGENTS.md。

---

## 安装

```bash
git clone https://github.com/jerryhuang/stockskill.git
cd stockskill
python3 -m pip install -r requirements.txt
```

依赖要点：`pandas`、`akshare`；全市场快照与 K 线建议安装 **`curl_cffi`**（`a-stock-shared`）。Web 需 `fastapi`、`uvicorn`、`openai`（及按需 `anthropic`）。

---

## 仓库结构（简要）

```text
.codex/skills/          # 各 Skill 的 SKILL.md 与 scripts
.codex/state/           # 本地状态（配置、自选、缓存等；部分已 .gitignore）
web/                    # FastAPI 服务、交易日历、静态前端
AGENTS.md               # Cursor / Agent 使用说明与注意事项
requirements.txt        # Python 依赖版本下限
```

---

## 数据来源与限制

- 行情与列表数据主要来自 **东方财富** 类接口（经 `fast_api` 限速与缓存）；部分接口经 **AkShare** 封装。
- **北向资金**：2024 年 8 月起成交净买入不再披露，以持股等数据为主。
- **非交易时段**：行情多为上一交易日收盘；休市 Worker 以 **`data-intel`** 为主，界面会标注「情报轮询、行情缓存」。

---

## 相关链接

- [AKShare](https://github.com/akfamily/akshare)
- 仓库：**https://github.com/jerryhuang/stockskill**

---

## 许可证与使用

使用本仓库即表示你理解市场有风险，并自行承担使用后果。请在合规前提下使用公开数据，勿将本工具输出作为唯一投资依据。
