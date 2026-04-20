#!/usr/bin/env python3
"""
A股投研自动化系统
- 后台 Worker 定时拉取数据 + 调用 LLM 生成完整分析报告
- Web 仅展示产出 + 提供设置界面
启动：python3 web/server.py（macOS 请用 python3；Worker 使用 sys.executable 调用 hub.py）
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import stat
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from cn_calendar import is_cn_sse_trading_day

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Paths ──
WEB_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_DIR.parent
STATE_DIR = REPO_ROOT / ".codex" / "state"
HUB_SCRIPT = REPO_ROOT / ".codex" / "skills" / "a-stock-research-hub" / "scripts" / "hub.py"
MONITOR_FILE = STATE_DIR / "monitor_latest.json"
LLM_CONFIG_FILE = STATE_DIR / "llm_config.json"
ANALYSIS_FILE = STATE_DIR / "analysis_latest.json"
WORKER_LOG_FILE = STATE_DIR / "worker_log.json"

SECRETS_DIR = Path.home() / ".config" / "stockskill"
SECRETS_FILE = SECRETS_DIR / "secrets.json"

STATE_DIR.mkdir(parents=True, exist_ok=True)
SECRETS_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ──
def _read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _llm_transient_error(exc: BaseException) -> bool:
    """429/529/503 或过载文案：可稍后重试，非密钥/参数错误。"""
    code = getattr(exc, "status_code", None)
    if code in (429, 503, 529):
        return True
    s = str(exc).lower()
    if "529" in s or "overloaded" in s or "rate limit" in s or "too many requests" in s:
        return True
    return False


def _write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, str(path))


# ── Secrets: obfuscated storage for API keys ──
_OBF_KEY = b"stockskill-lobster-2026-safe"

def _obfuscate(plaintext: str) -> str:
    data = plaintext.encode("utf-8")
    obf = bytes(b ^ _OBF_KEY[i % len(_OBF_KEY)] for i, b in enumerate(data))
    return base64.b64encode(obf).decode("ascii")


def _deobfuscate(encoded: str) -> str:
    obf = base64.b64decode(encoded.encode("ascii"))
    data = bytes(b ^ _OBF_KEY[i % len(_OBF_KEY)] for i, b in enumerate(obf))
    return data.decode("utf-8")


_SECRET_FIELDS = ("api_key", "api_base")


def _read_secrets() -> dict:
    raw = _read_json(SECRETS_FILE, {})
    result = {}
    for k, v in raw.items():
        if k in _SECRET_FIELDS and v:
            try:
                result[k] = _deobfuscate(v)
            except Exception:
                result[k] = v
        else:
            result[k] = v
    return result


def _write_secrets(data: dict):
    encoded = {}
    for k, v in data.items():
        if k in _SECRET_FIELDS and v:
            encoded[k] = _obfuscate(v)
        else:
            encoded[k] = v
    _write_json(SECRETS_FILE, encoded)
    try:
        os.chmod(SECRETS_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600
    except OSError:
        pass


def _read_full_config() -> dict:
    """Merge repo config (non-sensitive) + secrets (sensitive) into one dict."""
    cfg = _read_json(LLM_CONFIG_FILE, DEFAULT_LLM_CONFIG)
    if not isinstance(cfg, dict):
        cfg = dict(DEFAULT_LLM_CONFIG)
    secrets = _read_secrets()
    for field in _SECRET_FIELDS:
        if secrets.get(field):
            cfg[field] = secrets[field]
    return cfg


def _save_full_config(cfg: dict):
    """Split config: sensitive fields → secrets file, rest → repo config."""
    secret_data = _read_secrets()
    repo_cfg = {}
    for k, v in cfg.items():
        if k in _SECRET_FIELDS:
            if v:
                secret_data[k] = v
        else:
            repo_cfg[k] = v
    for field in _SECRET_FIELDS:
        repo_cfg.pop(field, None)
    _write_json(LLM_CONFIG_FILE, repo_cfg)
    _write_secrets(secret_data)


def _migrate_secrets_if_needed():
    """One-time migration: move plaintext api_key from llm_config.json to secrets."""
    repo_cfg = _read_json(LLM_CONFIG_FILE, {})
    if not isinstance(repo_cfg, dict):
        return
    migrated = False
    secrets = _read_secrets()
    for field in _SECRET_FIELDS:
        val = repo_cfg.get(field, "")
        if val and not secrets.get(field):
            secrets[field] = val
            migrated = True
    if migrated:
        _write_secrets(secrets)
        for field in _SECRET_FIELDS:
            repo_cfg.pop(field, None)
        _write_json(LLM_CONFIG_FILE, repo_cfg)
        print(f"  ✅ 已将敏感信息迁移到 {SECRETS_FILE}")
        print(f"     (文件权限: 仅所有者可读写)")


def _normalize_market(raw: dict) -> dict:
    if "data" in raw and isinstance(raw["data"], dict):
        inner = raw["data"]
        ms = inner.get("mechanical_stance", {})
        result = {
            "scan_time": raw.get("scan_time", inner.get("generated_at", "")),
            "indices": inner.get("indices", []),
            "breadth": inner.get("breadth", {}),
            "stance": ms.get("stance", "unknown") if isinstance(ms, dict) else "unknown",
            "stance_note": ms.get("note", "") if isinstance(ms, dict) else "",
            "themes": inner.get("themes", []),
            "screen_top": inner.get("screen", {}).get("top", []) if isinstance(inner.get("screen"), dict) else [],
            "open_trades": inner.get("open_trades", []),
            "discipline": inner.get("discipline", {}),
            "index_klines": inner.get("index_klines", {}),
            "watchlist": inner.get("watchlist", []),
        }
        if inner.get("intel"):
            result["intel"] = inner["intel"]
        if inner.get("data_mode"):
            result["data_mode"] = inner["data_mode"]
        if inner.get("quotes_note"):
            result["quotes_note"] = inner["quotes_note"]
        return result
    return raw


def _cn_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def is_cn_a_share_quote_session(dt: Optional[datetime] = None) -> bool:
    """
    A 股连续竞价时段（北京时间）：交易日 9:30–11:30、13:00–15:00。
    交易日以上交所日历为准（akshare 新浪源 + 本地缓存），含法定长假与调休工作日。
    """
    dt = dt or _cn_now()
    if not is_cn_sse_trading_day(dt.date()):
        return False
    m = dt.hour * 60 + dt.minute
    morning = (9 * 60 + 30) <= m <= (11 * 60 + 30)
    afternoon = (13 * 60) <= m < (15 * 60)
    return morning or afternoon


def _compute_sentiment(breadth: dict) -> dict:
    if not breadth:
        return {"score": 0, "max": 100, "level": "未知", "detail": {}}
    scores = {}
    r = breadth.get("ratio", 1)
    scores["涨跌比"] = 15 if r >= 2.5 else 12 if r >= 1.5 else 8 if r >= 1.0 else 5 if r >= 0.5 else 2
    lu = breadth.get("limit_up", 0)
    scores["涨停数"] = 18 if lu >= 120 else 15 if lu >= 80 else 10 if lu >= 50 else 6 if lu >= 20 else 3
    ld = breadth.get("limit_down", 0)
    scores["跌停数"] = 18 if ld <= 5 else 13 if ld <= 10 else 8 if ld <= 20 else 4 if ld <= 40 else 1
    m = breadth.get("mean_pct", 0)
    scores["均涨幅"] = 18 if m >= 2 else 15 if m >= 1 else 10 if m >= 0 else 5 if m >= -1 else 2
    u5 = breadth.get("up_gt5", 0)
    scores["强势股"] = 16 if u5 >= 300 else 12 if u5 >= 200 else 8 if u5 >= 100 else 4
    total = sum(scores.values())
    level = "极度亢奋" if total >= 75 else "活跃" if total >= 60 else "中性" if total >= 45 else "低迷" if total >= 30 else "冰点"
    return {"score": total, "max": 100, "level": level, "detail": scores}


# ═════════════════════════════════════════════════════════════
# Worker — 自动化引擎
# ═════════════════════════════════════════════════════════════
ANALYSIS_SYSTEM_PROMPT = """你是"龙虾参谋"—— 一个前瞻性 A 股投研情报系统。你的核心任务不是总结今天发生了什么，而是**预测未来 1~3 天和 1 周的市场走向**，并给出**具体可操作的投资建议**。

你会收到两类数据：
- **基础数据**：当日指数、涨跌统计、题材、选股结果
- **情报数据 (intel)**：多日 K 线技术指标、财经快讯、经济日历、板块资金流向、昨日涨停溢价、市场异动、北向资金、连板梯队

## 分析框架（按此顺序输出）

### 一、情报研判摘要
用 3-5 句话**定性**当前市场处于什么阶段（启动/加速/高潮/分歧/退潮/筑底），并说明依据。

### 二、技术信号矩阵
用表格列出主要指数的：收盘价 | 1日/3日/5日涨跌% | MA排列 | MACD信号 | RSI区域 | 连涨/跌天数 | 支撑位 | 压力位
对每个指数给出**趋势判断**（上涨/震荡/回调）。

### 三、情绪与资金动能分析
- 涨停溢价率（昨日涨停今日表现）→ **情绪先行信号**：是延续还是衰减？
- 连板梯队健康度 → 赚钱效应是否可持续
- 板块资金流向 → 钱在往哪个方向轮动？什么板块在被抛弃？
- 北向资金动向 → 外资态度
- 用这些信号综合判断：**短线情绪未来 1-3 天大概率是升温/持平/降温**

### 四、新闻与事件催化分析
- 从最近快讯中提取与 A 股直接相关的**催化因素**（政策、行业利好/利空、地缘、外围市场）
- 从经济日历中提取**未来 1-3 天将要公布的重要数据/事件**
- 判断这些催化因素对市场的**方向性影响**（利多/利空/中性）
- **不要罗列无关新闻**，只分析有实际市场影响的信息

### 五、未来走势预测（核心）
#### 短期预测（1~3 个交易日）
- **基准情景**（概率 X%）：预期走势描述 + 指数目标区间
- **乐观情景**（概率 Y%）：触发条件 + 走势描述
- **悲观情景**（概率 Z%）：触发条件 + 走势描述
- **关键验证信号**：明天盘中观察什么来确认/否定预测

#### 中期预测（1 周）
- 大盘方向判断 + 目标区间
- 主线题材是否有持续性
- 可能的转折点和触发因素

### 六、操作建议（必须具体可执行）
根据你的预测，给出**明确的操作指令**：

**情景 A（基准情景下）**：
- 如果明天 [具体条件]，则 [具体操作]
- 标的：代码 | 名称 | 买入区间 | 止损 | 目标 | 逻辑

**情景 B（乐观情景下）**：
- 如果 [具体条件成立]，则加仓/追入 [标的]

**情景 C（悲观情景下）**：
- 如果 [具体条件]，则 [减仓/空仓/回避]

**不推荐操作时**：明确说"当前观望，等待 [X条件] 再入场"

### 七、持仓纪律检查
- 如有持仓：逐笔检查止损(-5%) / 止盈(+15%) / 时间止损(10天)
- 如无持仓：是否满足入场条件

### 八、风险雷达
- 标注未来 3 天内最可能引爆的风险点
- 给出对应的防守策略

### 九、一句话结论
用一句话告诉我：**明天/本周应该做什么**

## 推理原则
- **基于证据推理**：每个预测必须指出支撑它的 2-3 个数据/信号
- **概率思维**：不要说"一定会涨"，而是给出情景概率
- **前瞻 > 回顾**：重心放在"接下来会怎样"而非"今天发生了什么"
- **信号冲突处理**：当技术面和情绪面发出矛盾信号时，说明矛盾点并给出综合判断

## 约束
- 资金约 7000 元，不买科创板(688)和创业板(300)
- 波段交易（约 2 周），手动执行，需要具体价位
- 纪律：止损-5%，止盈+15%，时间止损 10 天
- 关键数据用**加粗**，结构化信息用表格
- **禁止模棱两可**，必须给出明确的方向判断和操作建议"""

DEFAULT_LLM_CONFIG = {
    "api_base": "https://api.openai.com/v1",
    "api_key": "",
    "api_type": "openai",  # "openai" or "anthropic"
    "model": "gpt-4o",
    "temperature": 0.7,
    "max_tokens": 8192,
    "system_prompt": ANALYSIS_SYSTEM_PROMPT,
    "worker_interval_min": 45,
    "worker_interval_off_hours_min": 120,
    "worker_auto_start": True,
}


class Worker:
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.status = "stopped"          # stopped/idle/busy/error
        self.phase = ""                   # collecting/screening/analyzing
        self.message = ""                 # human-readable current step
        self.progress = 0                 # 0-100
        self.last_run: Optional[str] = None
        self.last_error: Optional[str] = None
        self.next_run: Optional[str] = None
        self.cycle_count = 0
        self.cycle_start: Optional[float] = None
        self.steps: list = []             # [{name, status, elapsed_s}]

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _elapsed(self) -> int:
        return int(time.time() - self.cycle_start) if self.cycle_start else 0

    def _set(self, phase: str, msg: str, progress: int):
        self.phase = phase
        self.message = msg
        self.progress = progress
        _log_worker(f"[{self._ts()}] [{progress}%] {msg}")

    @property
    def state(self) -> dict:
        return {
            "status": self.status,
            "phase": self.phase,
            "message": self.message,
            "progress": self.progress,
            "elapsed_sec": self._elapsed(),
            "steps": self.steps,
            "last_run": self.last_run,
            "last_error": self.last_error,
            "next_run": self.next_run,
            "cycle_count": self.cycle_count,
        }

    def start(self):
        if self.running:
            return
        self.running = True
        self.status = "idle"
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.status = "stopped"
        self.phase = ""
        self.message = "已停止"
        self.progress = 0

    def trigger_once(self):
        threading.Thread(target=lambda: self._run_cycle(force_full=True), daemon=True).start()

    def _loop(self):
        first = True
        while self.running:
            cfg = _read_full_config()
            trading = is_cn_a_share_quote_session()
            interval = int(cfg.get("worker_interval_min", 45))
            off_iv = int(cfg.get("worker_interval_off_hours_min", 120))
            use_iv = interval if trading else max(15, off_iv)
            if not first:
                wake_at = time.time() + use_iv * 60
                self.next_run = datetime.fromtimestamp(wake_at).strftime("%H:%M:%S")
                self.status = "idle"
                self.phase = "waiting"
                mode_lbl = "连续竞价·全量行情" if trading else "休市·仅情报"
                self.message = f"等待下一轮（{self.next_run}，每{use_iv}分钟·{mode_lbl}）"
                self.progress = 0
                while self.running and time.time() < wake_at:
                    time.sleep(5)
                if not self.running:
                    break
            first = False
            self._run_cycle(force_full=False)

    def _run_cycle(self, force_full: bool = False):
        self.status = "busy"
        self.last_error = None
        self.cycle_start = time.time()
        self.steps = []

        trading = is_cn_a_share_quote_session()
        use_full = bool(force_full or trading)

        # ── Step 1: Collect market data ──
        if use_full:
            self._set("collecting", "交易时段：拉取全市场行情、选股与情报…预计2~3分钟", 5)
            mode = "full"
        else:
            self._set("collecting", "休市：仅刷新情报/快讯（不重复拉取全市场行情快照）", 5)
            mode = "intel_only"
        step1_start = time.time()
        market = self._collect_data(mode)
        step1_sec = int(time.time() - step1_start)

        if not market:
            self.steps.append({"name": "数据采集", "icon": "❌", "detail": self.last_error or "失败", "sec": step1_sec})
            self._set("error", f"数据采集失败: {self.last_error or '未知错误'}", 0)
            self.status = "error"
            return

        step_title = "数据采集（全量）" if use_full else "情报侦测（行情缓存）"
        self.steps.append({"name": step_title, "icon": "✅", "detail": "成功", "sec": step1_sec})
        self.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cycle_count += 1
        self._set("collecting", f"数据采集完成（{step1_sec}秒）", 50)

        # ── Step 2: AI Analysis ──
        cfg = _read_full_config()
        if cfg.get("api_key"):
            model_name = cfg.get("model", "?")
            self._set("analyzing", f"正在调用 {model_name} 生成分析报告…预计30~60秒", 55)
            step2_start = time.time()
            analysis = self._generate_analysis(market, cfg)
            step2_sec = int(time.time() - step2_start)

            if analysis:
                self.steps.append({"name": f"AI分析({model_name})", "icon": "✅", "detail": f"{len(analysis)}字", "sec": step2_sec})
                _write_json(ANALYSIS_FILE, {
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "data_time": market.get("scan_time", ""),
                    "model": model_name,
                    "content": analysis,
                    "status": "success",
                })
                self._set("done", f"分析报告已生成（{len(analysis)}字，耗时{step2_sec}秒）", 100)
            else:
                self.steps.append({"name": f"AI分析({model_name})", "icon": "❌", "detail": self.last_error or "失败", "sec": step2_sec})
                self._set("error", f"AI分析失败: {self.last_error or '未知错误'}", 50)
        else:
            self.steps.append({"name": "AI分析", "icon": "⏭", "detail": "未配置API Key，已跳过", "sec": 0})
            self._set("done", "数据采集完成（未配置API Key，跳过AI分析）", 100)

        total_sec = int(time.time() - self.cycle_start)
        self.steps.append({"name": "总耗时", "icon": "⏱", "detail": f"{total_sec}秒", "sec": total_sec})
        self.status = "idle" if self.running else "stopped"

    def _collect_data(self, mode: str = "full") -> Optional[dict]:
        try:
            hub_args = [sys.executable, str(HUB_SCRIPT), "data"]
            if mode == "intel_only":
                hub_args = [sys.executable, str(HUB_SCRIPT), "data-intel"]
            proc = subprocess.Popen(
                hub_args,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=str(REPO_ROOT),
            )
            # Poll with progress updates
            while proc.poll() is None:
                elapsed = self._elapsed()
                if mode == "intel_only":
                    pct = min(40, 8 + elapsed // 2)
                    self.message = f"情报采集中…已运行 {elapsed} 秒"
                else:
                    if elapsed < 30:
                        pct = 10
                    elif elapsed < 60:
                        pct = 20
                    elif elapsed < 120:
                        pct = 30
                    else:
                        pct = 40
                    self.message = f"数据采集中…已运行 {elapsed} 秒"
                self.progress = pct
                time.sleep(3)

            stdout, stderr = proc.communicate(timeout=10)
            if proc.returncode != 0:
                self.last_error = (stderr or "exit code != 0")[:300]
                return None
            parsed = json.loads(stdout)
            wrapped = {"scan_time": parsed.get("generated_at", ""), "data": parsed}
            _write_json(MONITOR_FILE, wrapped)
            return _normalize_market(wrapped)
        except subprocess.TimeoutExpired:
            proc.kill()
            self.last_error = "数据采集超时（>10分钟）"
            return None
        except json.JSONDecodeError as e:
            self.last_error = f"JSON解析失败: {e}"
            return None
        except Exception as e:
            self.last_error = str(e)[:300]
            return None

    def _generate_analysis(self, market: dict, cfg: dict) -> Optional[str]:
        data_text = json.dumps(market, ensure_ascii=False, indent=2)
        extra = ""
        if market.get("data_mode") == "intel_only":
            extra = (
                "\n\n【本轮为休市/非连续竞价情报轮询】"
                "指数、涨跌统计、题材、选股、自选技术指标等为**上一轮全量快照（可能已过时）**，"
                "请勿当作实时盘口。**请优先根据 intel 情报块（快讯、日历、资金面等）**评估消息面对下一交易时段及短线走势的影响；"
                "若情报不足以推翻此前判断，可明确写“维持上一交易日结论，待开盘验证”。\n"
            )
        user_content = f"以下是当前A股市场数据（JSON）。请生成完整分析报告：{extra}\n\n```json\n{data_text}\n```"
        self.message = f"正在等待 {cfg.get('model','?')} 响应…"

        api_type = cfg.get("api_type", "openai")
        if api_type == "anthropic":
            return self._call_anthropic(cfg, user_content)
        return self._call_openai(cfg, user_content)

    def _call_openai(self, cfg: dict, user_content: str) -> Optional[str]:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=cfg["api_key"],
                base_url=cfg.get("api_base", "https://api.openai.com/v1"),
                timeout=120,
            )
            resp = client.chat.completions.create(
                model=cfg.get("model", "gpt-4o"),
                messages=[
                    {"role": "system", "content": cfg.get("system_prompt", ANALYSIS_SYSTEM_PROMPT)},
                    {"role": "user", "content": user_content},
                ],
                temperature=cfg.get("temperature", 0.7),
                max_tokens=cfg.get("max_tokens", 8192),
            )
            return resp.choices[0].message.content
        except Exception as e:
            self.last_error = str(e)[:300]
            return None

    def _call_anthropic(self, cfg: dict, user_content: str) -> Optional[str]:
        import anthropic
        client = anthropic.Anthropic(
            api_key=cfg["api_key"],
            base_url=cfg.get("api_base", "https://api.anthropic.com"),
            timeout=300.0,
        )
        max_attempts = 4
        last_err: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                resp = client.messages.create(
                    model=cfg.get("model", "claude-sonnet-4-20250514"),
                    max_tokens=cfg.get("max_tokens", 8192),
                    system=cfg.get("system_prompt", ANALYSIS_SYSTEM_PROMPT),
                    messages=[{"role": "user", "content": user_content}],
                    temperature=cfg.get("temperature", 0.7),
                )
                parts = [b.text for b in resp.content if getattr(b, "text", None) is not None]
                return "\n".join(parts) if parts else None
            except Exception as e:
                last_err = e
                if attempt < max_attempts - 1 and _llm_transient_error(e):
                    wait = 2 ** attempt
                    _log_worker(f"[LLM] 上游繁忙(529/429等)，{wait}s 后重试 ({attempt + 1}/{max_attempts})")
                    time.sleep(wait)
                    continue
                self.last_error = str(e)[:300]
                return None
        if last_err:
            self.last_error = str(last_err)[:300]
        return None


worker = Worker()


def _log_worker(msg: str):
    logs = _read_json(WORKER_LOG_FILE, [])
    if not isinstance(logs, list):
        logs = []
    logs.append(msg)
    logs = logs[-50:]  # keep last 50
    _write_json(WORKER_LOG_FILE, logs)


# ═════════════════════════════════════════════════════════════
# FastAPI App
# ═════════════════════════════════════════════════════════════
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    _migrate_secrets_if_needed()
    cfg = _read_full_config()
    has_key = bool(cfg.get("api_key"))
    print(f"  📂 配置文件: {LLM_CONFIG_FILE}")
    print(f"  🔐 密钥文件: {SECRETS_FILE}")
    print(f"  🤖 模型: {cfg.get('model', '未设置')}")
    print(f"  🔑 API Key: {'已配置' if has_key else '❌ 未配置'}")
    if cfg.get("worker_auto_start", True):
        worker.start()
    yield
    worker.stop()


app = FastAPI(title="A股投研自动化系统", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Data ──
@app.get("/api/data")
async def get_data():
    raw = _read_json(MONITOR_FILE)
    if not raw:
        return JSONResponse({"error": "暂无数据，Worker 正在初始化..."}, status_code=404)
    data = _normalize_market(raw)
    data["sentiment"] = _compute_sentiment(data.get("breadth", {}))
    return JSONResponse(data)


# ── Analysis ──
@app.get("/api/analysis")
async def get_analysis():
    analysis = _read_json(ANALYSIS_FILE)
    if not analysis:
        return JSONResponse({"status": "none", "content": ""})
    return JSONResponse(analysis)


# ── Manual analysis with streaming ──
@app.post("/api/analyze")
async def analyze_stream(request: Request):
    body = await request.json()
    user_msg = body.get("message", "请基于以上市场数据进行全面分析。")
    cfg = _read_full_config()
    if not cfg.get("api_key"):
        return JSONResponse({"error": "请先配置 API Key"}, status_code=400)

    raw = _read_json(MONITOR_FILE)
    market = _normalize_market(raw) if raw else {}
    data_text = json.dumps(market, ensure_ascii=False, indent=2)
    intel_hint = ""
    if market.get("data_mode") == "intel_only":
        intel_hint = (
            "【当前快照为情报轮询模式：行情类字段可能非实时，请优先结合 intel 与用户问题作答】\n\n"
        )
    user_content = f"{intel_hint}市场数据：\n```json\n{data_text}\n```\n\n{user_msg}"
    api_type = cfg.get("api_type", "openai")
    logger.info(
        "analyze_stream start api_type=%s model=%s user_chars=%d payload_chars=%d scan_time=%s",
        api_type,
        cfg.get("model", ""),
        len(user_msg),
        len(user_content),
        market.get("scan_time", ""),
    )
    _log_worker(
        f"[{datetime.now().strftime('%H:%M:%S')}] 手动分析请求 api={api_type} model={cfg.get('model','')} user≈{len(user_msg)}字 上下文≈{len(user_content)}字"
    )

    if api_type == "anthropic":
        return StreamingResponse(_stream_anthropic(cfg, user_content, market), media_type="text/event-stream")
    return StreamingResponse(_stream_openai(cfg, user_content, market), media_type="text/event-stream")


async def _stream_openai(cfg: dict, user_content: str, market: dict):
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield f"data: {json.dumps({'error': 'pip install openai'}, ensure_ascii=False)}\n\n"
        return

    t0 = time.time()
    client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg.get("api_base", "https://api.openai.com/v1"))
    full = ""
    try:
        stream = await client.chat.completions.create(
            model=cfg.get("model", "gpt-4o"),
            messages=[
                {"role": "system", "content": cfg.get("system_prompt", ANALYSIS_SYSTEM_PROMPT)},
                {"role": "user", "content": user_content},
            ],
            temperature=cfg.get("temperature", 0.7),
            max_tokens=cfg.get("max_tokens", 8192),
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                c = chunk.choices[0].delta.content
                full += c
                yield f"data: {json.dumps({'content': c}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
        dt = time.time() - t0
        logger.info(
            "analyze_stream openai ok model=%s reply_chars=%d elapsed_sec=%.2f",
            cfg.get("model", ""),
            len(full),
            dt,
        )
        _log_worker(
            f"[{datetime.now().strftime('%H:%M:%S')}] 手动分析完成(openai) {len(full)}字 耗时{dt:.1f}s"
        )
        _write_json(ANALYSIS_FILE, {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_time": market.get("scan_time", ""),
            "model": cfg.get("model", ""),
            "content": full,
            "status": "success",
        })
    except Exception as e:
        dt = time.time() - t0
        logger.warning(
            "analyze_stream openai fail model=%s elapsed_sec=%.2f err=%s",
            cfg.get("model", ""),
            dt,
            str(e)[:400],
        )
        _log_worker(
            f"[{datetime.now().strftime('%H:%M:%S')}] 手动分析失败(openai) {dt:.1f}s: {str(e)[:200]}"
        )
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"


async def _stream_anthropic(cfg: dict, user_content: str, market: dict):
    try:
        import anthropic
    except ImportError:
        yield f"data: {json.dumps({'error': 'pip install anthropic'}, ensure_ascii=False)}\n\n"
        return

    client = anthropic.AsyncAnthropic(
        api_key=cfg["api_key"],
        base_url=cfg.get("api_base", "https://api.anthropic.com"),
        timeout=300.0,
    )
    max_attempts = 4
    last_err: Optional[Exception] = None
    for attempt in range(max_attempts):
        full = ""
        t0 = time.time()
        try:
            async with client.messages.stream(
                model=cfg.get("model", "claude-sonnet-4-20250514"),
                max_tokens=cfg.get("max_tokens", 8192),
                system=cfg.get("system_prompt", ANALYSIS_SYSTEM_PROMPT),
                messages=[{"role": "user", "content": user_content}],
                temperature=cfg.get("temperature", 0.7),
            ) as stream:
                async for text in stream.text_stream:
                    full += text
                    yield f"data: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            dt = time.time() - t0
            logger.info(
                "analyze_stream anthropic ok model=%s reply_chars=%d elapsed_sec=%.2f attempt=%d",
                cfg.get("model", ""),
                len(full),
                dt,
                attempt + 1,
            )
            _log_worker(
                f"[{datetime.now().strftime('%H:%M:%S')}] 手动分析完成(anthropic) {len(full)}字 耗时{dt:.1f}s"
            )
            _write_json(ANALYSIS_FILE, {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data_time": market.get("scan_time", ""),
                "model": cfg.get("model", ""),
                "content": full,
                "status": "success",
            })
            return
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1 and _llm_transient_error(e):
                wait = 2 ** attempt
                logger.info(
                    "analyze_stream anthropic retry after %s attempt=%d/%d wait=%ds",
                    type(e).__name__,
                    attempt + 1,
                    max_attempts,
                    wait,
                )
                msg = f"\n[上游繁忙，{wait}秒后自动重试 {attempt + 2}/{max_attempts}]\n"
                yield f"data: {json.dumps({'content': msg}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(wait)
                continue
            dt = time.time() - t0
            logger.warning(
                "analyze_stream anthropic fail model=%s elapsed_sec=%.2f err=%s",
                cfg.get("model", ""),
                dt,
                str(e)[:400],
            )
            _log_worker(
                f"[{datetime.now().strftime('%H:%M:%S')}] 手动分析失败(anthropic) {dt:.1f}s: {str(e)[:200]}"
            )
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            return
    if last_err:
        yield f"data: {json.dumps({'error': str(last_err)}, ensure_ascii=False)}\n\n"


# ── Worker control ──
@app.get("/api/worker")
async def worker_status():
    return JSONResponse(worker.state)


@app.post("/api/worker/start")
async def worker_start():
    worker.start()
    return JSONResponse({"status": "started"})


@app.post("/api/worker/stop")
async def worker_stop():
    worker.stop()
    return JSONResponse({"status": "stopped"})


@app.post("/api/worker/trigger")
async def worker_trigger():
    worker.trigger_once()
    return JSONResponse({"status": "triggered"})


@app.get("/api/worker/logs")
async def worker_logs():
    return JSONResponse(_read_json(WORKER_LOG_FILE, []))


# ── Config ──
@app.get("/api/config")
async def get_config():
    cfg = _read_full_config()
    safe = dict(cfg)
    key = safe.pop("api_key", "")
    safe["api_key_masked"] = (key[:8] + "..." + key[-4:]) if len(key) > 12 else ("***" if key else "")
    safe["api_key_saved"] = bool(key)
    safe["secrets_path"] = str(SECRETS_FILE)
    return JSONResponse(safe)


class ConfigUpdate(BaseModel):
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    api_type: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    worker_interval_min: Optional[int] = None
    worker_interval_off_hours_min: Optional[int] = None
    worker_auto_start: Optional[bool] = None


@app.post("/api/config")
async def save_config(update: ConfigUpdate):
    cfg = _read_full_config()
    for field, value in update.dict(exclude_none=True).items():
        cfg[field] = value
    _save_full_config(cfg)
    return JSONResponse({"status": "ok"})


# ── Trades ──
@app.get("/api/trades")
async def get_trades():
    return JSONResponse(_read_json(STATE_DIR / "trades.json", []))


# ── Static ──
@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "static" / "index.html")


static_dir = WEB_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  🦞 A股投研自动化系统")
    print("  http://localhost:8888")
    print("  Worker 自动启动，定时拉取数据 + AI 分析")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
