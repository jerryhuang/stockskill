#!/usr/bin/env python3
"""
A 股交易日历（以上交所交易日为准）
- 数据源：akshare.tool_trade_date_hist_sina（与交易所日历一致，含调休工作日）
- 缓存：.codex/state/trade_calendar_sse.json，默认 7 天刷新
- 覆盖：.codex/state/trading_calendar_override.json（强制休市 / 强制开市）
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
_STATE_DIR = _REPO_ROOT / ".codex" / "state"
_CAL_CACHE = _STATE_DIR / "trade_calendar_sse.json"
_OVERRIDE = _STATE_DIR / "trading_calendar_override.json"

_DEFAULT_CACHE_TTL_SEC = 7 * 24 * 3600


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_overrides() -> Tuple[Set[str], Set[str]]:
    raw = _load_json(_OVERRIDE, {})
    if not isinstance(raw, dict):
        return set(), set()
    closed = raw.get("force_closed_dates") or raw.get("closed") or []
    opened = raw.get("force_open_dates") or raw.get("open") or []
    if not isinstance(closed, list):
        closed = []
    if not isinstance(opened, list):
        opened = []
    return {str(x)[:10] for x in closed}, {str(x)[:10] for x in opened}


def _fetch_sse_dates_from_network() -> Set[str]:
    import akshare as ak

    df = ak.tool_trade_date_hist_sina()
    if df is None or df.empty:
        return set()
    return set(df["trade_date"].astype(str).tolist())


def get_sse_trade_dates(refresh: bool = False) -> Set[str]:
    """返回历史上交所交易日集合（YYYY-MM-DD）。"""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if not refresh and _CAL_CACHE.exists():
        try:
            j = json.loads(_CAL_CACHE.read_text(encoding="utf-8"))
            ts = float(j.get("fetched_at", 0))
            days = j.get("trade_dates")
            if isinstance(days, list) and (now - ts) < _DEFAULT_CACHE_TTL_SEC:
                return set(str(x) for x in days)
        except Exception:
            pass

    dates = _fetch_sse_dates_from_network()
    if not dates and _CAL_CACHE.exists():
        try:
            j = json.loads(_CAL_CACHE.read_text(encoding="utf-8"))
            days = j.get("trade_dates")
            if isinstance(days, list):
                return set(str(x) for x in days)
        except Exception:
            pass

    if dates:
        payload = {
            "fetched_at": now,
            "source": "akshare.tool_trade_date_hist_sina",
            "trade_dates": sorted(dates),
        }
        tmp = f"{_CAL_CACHE}.{int(now)}.tmp"
        Path(tmp).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        Path(tmp).replace(_CAL_CACHE)

    return dates


def is_cn_sse_trading_day(d: Optional[date] = None) -> bool:
    """
    是否为 A 股交易日（上交所日历 + 可选覆盖）。
    网络与缓存均失败时，退化为「周一至周五」仅作兜底（长假仍可能误判）。
    """
    if d is None:
        d = datetime.now().date()
    ds = d.isoformat()
    closed, opened = _load_overrides()
    if ds in closed:
        return False
    if ds in opened:
        return True
    dates = get_sse_trade_dates()
    if dates:
        return ds in dates
    return d.weekday() < 5


def override_template() -> Dict[str, Any]:
    return {
        "force_closed_dates": [],
        "force_open_dates": [],
        "_comment": "force_closed_dates: 额外休市；force_open_dates: 日历未更新时的临时调休上班日",
    }
