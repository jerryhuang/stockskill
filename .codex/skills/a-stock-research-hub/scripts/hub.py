#!/usr/bin/env python3
"""
投研编排中枢（云端可跑）：
- 短线：晨报 / 盘中扫描 / 收盘复盘
- 波段（约两周）：swing 参谋简报（少看盘节奏 + 指数近况 + 自选 MA 位置）
- watchlist + 新闻/公告关键词触发；告警去重（TTL）
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "../../../.."))
_STATE_DIR = os.path.join(_REPO_ROOT, ".codex", "state")
_REPORTS_DIR = os.path.join(_STATE_DIR, "reports")

os.makedirs(_STATE_DIR, exist_ok=True)
os.makedirs(_REPORTS_DIR, exist_ok=True)

# Add skill script roots so we can import their functions if needed
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "../../a-stock-shared/scripts")))


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{time.time_ns()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _default_config() -> Dict[str, Any]:
    # 短线默认阈值：保守取值，避免刷屏
    return {
        "dedup_ttl_sec": 60 * 60 * 4,  # 同类告警 4h 内只提示一次
        "risk": {
            "breadth_ratio_weak": 0.5,     # 涨跌比<0.5 视为偏弱
            "breadth_ratio_strong": 1.2,   # 涨跌比>1.2 视为偏强
            "limit_down_risk": 15,         # 跌停>=15 风险升高
            "limit_up_good": 80,           # 涨停>=80 赚钱效应较好
            "down_gt5_risk": 300,          # 跌幅>5%家数过多（来自全市场快照）
        },
        "watchlist": {
            "max_items": 50,
            "keywords_max": 50,
        },
        "report": {
            "top_theme_n": 8,
            "top_watch_n": 10,
        },
        "news": {
            "enabled_in_scan": True,
            "flash_count": 50,
            "announce_count_per_stock": 8,
            "flash_non_risk_require_watch_keyword": True,
            "ignore_terms": ["STOXX", "State Street"],
            "keyword_level": {
                "风险": ["立案", "处罚", "监管处罚", "退市", "终止上市", "ST", "风险提示", "诉讼", "仲裁"],
                "关注": ["减持", "质押", "解禁", "问询函", "关注函", "延期", "终止", "变更", "亏损"],
                "信息": ["回购", "增持", "业绩预告", "预增", "中标", "签订", "重大合同", "分红"],
            },
        },
        # 波段持有（约 10 个交易日 / 2 周）：偏低频决策，配套「参谋」输出
        "swing": {
            "hold_days_target": 10,
            "review_per_week": 2,
            "ma_window": 20,
            "watchlist_snapshot_max": 10,
            "index_kline_days": 12,
        },
    }


def _config_path() -> str:
    return os.path.join(_STATE_DIR, "config.json")


def _watchlist_path() -> str:
    return os.path.join(_STATE_DIR, "watchlist.json")


def _alerts_seen_path() -> str:
    return os.path.join(_STATE_DIR, "alerts_seen.json")


def _market_last_path() -> str:
    return os.path.join(_STATE_DIR, "market_last.json")


def ensure_state_files() -> None:
    cfg_path = _config_path()
    if not os.path.exists(cfg_path):
        _save_json(cfg_path, _default_config())
    else:
        # 轻量“迁移”：补齐新字段
        cfg = _load_json(cfg_path, {})
        if not isinstance(cfg, dict):
            cfg = {}
        merged = _default_config()
        # shallow merge
        for k, v in cfg.items():
            merged[k] = v
        # nested merge for news
        if isinstance(cfg.get("news"), dict):
            merged_news = _default_config()["news"]
            merged_news.update(cfg["news"])
            merged["news"] = merged_news
        if isinstance(cfg.get("swing"), dict):
            merged_swing = _default_config()["swing"]
            merged_swing.update(cfg["swing"])
            merged["swing"] = merged_swing
        _save_json(cfg_path, merged)

    wl_path = _watchlist_path()
    if not os.path.exists(wl_path):
        _save_json(
            wl_path,
            {
                "stocks": [
                    {
                        "code": "600519",
                        "thesis": "示例：基本面/景气度/事件驱动逻辑",
                        "buy_zone": "",
                        "stop_loss": "",
                        "invalid_if": "",
                        "target_days": 10,
                    }
                ],
                "keywords": ["回购", "增持", "业绩预告", "重大合同", "监管", "立案", "减持"],
                "blacklist": [],
            },
        )

    seen_path = _alerts_seen_path()
    if not os.path.exists(seen_path):
        _save_json(seen_path, {})

    last_path = _market_last_path()
    if not os.path.exists(last_path):
        _save_json(last_path, {})


# ─────────────────────────────────────────────────────────────
# Data acquisition helpers (prefer fast_api; fallback to akshare)
# ─────────────────────────────────────────────────────────────
def _get_all_spot_df():
    from fast_api import get_all_a_stock_spot

    return get_all_a_stock_spot()


def _breadth_stats_from_spot(df) -> Dict[str, Any]:
    import pandas as pd

    valid = df[pd.notna(df["涨跌幅"])].copy()
    non_st = valid[~valid["名称"].str.contains("ST|退市", na=False)]
    pct = non_st["涨跌幅"].astype(float)
    total = len(pct)
    up = int((pct > 0).sum())
    down = int((pct < 0).sum())
    flat = int((pct == 0).sum())
    limit_up = int((pct >= 9.9).sum())
    limit_down = int((pct <= -9.9).sum())
    up_gt5 = int((pct >= 5).sum())
    down_gt5 = int((pct <= -5).sum())
    ratio = up / max(down, 1)
    mean_pct = float(pct.mean()) if total else 0.0

    return {
        "total": total,
        "up": up,
        "down": down,
        "flat": flat,
        "limit_up": limit_up,
        "limit_down": limit_down,
        "up_gt5": up_gt5,
        "down_gt5": down_gt5,
        "ratio": ratio,
        "mean_pct": mean_pct,
    }


def _index_quotes_df():
    from fast_api import get_index_quotes

    return get_index_quotes()


def _normalize_stock_code(code: str) -> str:
    code = (code or "").strip()
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if code.startswith(p):
            return code[2:]
    return code


def _watchlist_entries(wl: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = []
    for item in wl.get("stocks", []) or []:
        if isinstance(item, dict):
            code = _normalize_stock_code(str(item.get("code", "")))
            if code:
                obj = dict(item)
                obj["code"] = code
                entries.append(obj)
        else:
            code = _normalize_stock_code(str(item))
            if code:
                entries.append({"code": code})
    return entries


def _keyword_match_level(
    text: str,
    kw_levels: Dict[str, List[str]],
    watch_keywords: List[str],
    ignore_terms: List[str],
) -> Tuple[Optional[str], Optional[str], bool]:
    t = text or ""
    upper_t = t.upper()
    for term in ignore_terms:
        if term and term.upper() in upper_t:
            return None, None, False

    def _contains_st_risk(s: str) -> bool:
        # 避免把 STOXX 等英文串误判为 ST 风险
        patterns = [
            r"\*ST",
            r"ST[\u4e00-\u9fa5A-Za-z0-9]{1,8}",
            r"被实施ST",
            r"ST风险",
        ]
        return any(re.search(p, s, re.IGNORECASE) for p in patterns)

    for lvl in ["风险", "关注", "信息"]:
        for kw in kw_levels.get(lvl, []) or []:
            if not kw:
                continue
            if kw == "ST":
                if _contains_st_risk(t):
                    return lvl, kw, False
                continue
            if kw in t:
                return lvl, kw, False

    for kw in watch_keywords:
        if kw and kw in t:
            return "关注", kw, True

    return None, None, False


def _index_kline_recent(secid: str, n: int = 12) -> Optional[Tuple[str, str, float, float, float]]:
    """返回 (起始日, 结束日, 区间涨跌%, 区间振幅%, 最新收盘) 或 None。"""
    params = {
        "secid": secid,
        "klt": "101",
        "fqt": "1",
        "lmt": str(max(5, min(int(n), 30))),
        "end": "20500101",
        "beg": "0",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    j = None
    try:
        from curl_cffi import requests as curlreq

        r = curlreq.get(url, params=params, timeout=30, impersonate="chrome110")
        j = r.json()
    except Exception:
        try:
            import requests as _rq

            r = _rq.get(
                url,
                params=params,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Referer": "https://quote.eastmoney.com/",
                },
            )
            j = r.json()
        except Exception:
            return None

    try:
        kl = (j or {}).get("data", {}).get("klines", [])
        if not kl:
            return None
        take = max(5, min(int(n), 30))
        kl = kl[-take:]
        rows = []
        for s in kl:
            parts = s.split(",")
            if len(parts) >= 5:
                d, _o, c, h, low = parts[0], parts[1], parts[2], parts[3], parts[4]
                rows.append((d, float(c), float(h), float(low)))
        if not rows:
            return None
        start_d, start_c, _, _ = rows[0]
        end_d, end_c, hi, lo = rows[-1][0], rows[-1][1], max(r[2] for r in rows), min(r[3] for r in rows)
        chg = (end_c - start_c) / start_c * 100 if start_c else 0.0
        amp = (hi - lo) / start_c * 100 if start_c else 0.0
        return start_d, end_d, round(chg, 2), round(amp, 2), end_c
    except Exception:
        return None


def _swing_stock_row(code: str, ma_w: int) -> Optional[Dict[str, Any]]:
    import akshare as ak

    code = _normalize_stock_code(code)
    if not code or not code.isdigit():
        return None
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df is None or df.empty or len(df) < ma_w + 2:
            return None
        close_col = next((c for c in df.columns if "收盘" in str(c)), None)
        if not close_col:
            return None
        s = df[close_col].astype(float)
        last = float(s.iloc[-1])
        ma = float(s.tail(ma_w).mean())
        base5 = float(s.iloc[-6]) if len(s) >= 6 else float(s.iloc[0])
        ret5 = (last / base5 - 1) * 100 if base5 else 0.0
        pos = "站上MA" if last >= ma else "跌破MA"
        return {
            "代码": code,
            "收盘": round(last, 2),
            f"MA{ma_w}": round(ma, 2),
            "vsMA": pos,
            "近5日%": round(ret5, 2),
        }
    except Exception:
        return None


def swing_advisor_brief() -> None:
    """波段（约两周）参谋简报：低频节奏 + 环境 + 自选技术位（非荐股）。"""
    ensure_state_files()
    cfg = _load_json(_config_path(), _default_config())
    sw = cfg.get("swing", {}) if isinstance(cfg.get("swing"), dict) else {}
    hold = int(sw.get("hold_days_target", 10))
    reviews = int(sw.get("review_per_week", 2))
    ma_w = int(sw.get("ma_window", 20))
    wl_max = int(sw.get("watchlist_snapshot_max", 10))
    kdays = int(sw.get("index_kline_days", 12))

    wl = _load_json(_watchlist_path(), {"stocks": [], "keywords": [], "blacklist": []})
    bl = set(str(x) for x in (wl.get("blacklist") or []))
    entries = [e for e in _watchlist_entries(wl) if e["code"] not in bl][:wl_max]

    print("=" * 72)
    print(f"🦞 A股波段参谋（目标持有约{hold}个交易日）  {_now_str()}")
    print("=" * 72)

    print("\n【军师角色说明】")
    print("- 目标：少看盘、2 周左右决策节奏；输出为**环境与自选体检**，不代替你下单。")
    print("- 你只需自选里放**已经研究过、愿意拿 2 周**的标的；参谋帮你盯**指数+技术位+公告关键词**。")
    print(f"- 建议节奏：每周主动看 **{reviews}** 次本简报 + 收盘后跑一次 `hub.py close`；异动时跑 `hub.py scan`。")

    print("\n【买入/卖出纪律模板（请自己填具体价位）】")
    print("- 买入：只在**指数环境不过度恶化**、且个股**逻辑未破坏**时分批；单票仓位上限自行定。")
    print("- 卖出三类触发（缺一不可地写在纸上）：①触及止损价 ②持有满/到 2 周仍无表现且走弱 ③逻辑或公告证伪")

    print("\n【环境：主要指数快照】")
    try:
        idx = _index_quotes_df()
        if idx is not None and not idx.empty:
            for name in ["上证指数", "深证成指", "创业板指", "科创50", "沪深300", "中证1000"]:
                sub = idx[idx["指数"] == name]
                if not sub.empty:
                    r = sub.iloc[0]
                    print(f"- {name}: {float(r['最新价']):.2f}  ({float(r['涨跌幅']):.2f}%)")
        else:
            print("- 暂无法获取指数快照")
    except Exception as e:
        print(f"- 指数快照不可用: {e}")

    print("\n【环境：上证近段走势（约{}根日K）】".format(kdays))
    k = _index_kline_recent("1.000001", n=kdays)
    if k:
        a, b, chg, amp, cls = k
        print(f"- 区间 {a} ~ {b}  上证收盘约 {cls:.2f}  区间涨跌 {chg}%  振幅 {amp}%")
    else:
        print("- 上证日线序列暂不可用")

    print("\n【自选体检（收盘 vs MA，仅技术位）】")
    if not entries:
        print("- watchlist 无股票。请执行: `hub.py watchlist add-stock 你的代码`")
    else:
        for entry in entries:
            c = entry["code"]
            row = _swing_stock_row(c, ma_w)
            if row:
                print(
                    f"- {row['代码']}: 收盘 {row['收盘']}  {row[f'MA{ma_w}']}  "
                    f"{row['vsMA']}{ma_w}  近5日 {row['近5日%']}%"
                )
                plan_bits = []
                if entry.get("buy_zone"):
                    plan_bits.append(f"买入区间={entry['buy_zone']}")
                if entry.get("stop_loss"):
                    plan_bits.append(f"止损={entry['stop_loss']}")
                if entry.get("invalid_if"):
                    plan_bits.append(f"失效条件={entry['invalid_if']}")
                if entry.get("target_days"):
                    plan_bits.append(f"目标持有={entry['target_days']}天")
                if entry.get("thesis"):
                    plan_bits.append(f"逻辑={entry['thesis']}")
                if plan_bits:
                    print(f"  计划: {' | '.join(plan_bits)}")
            else:
                print(f"- {c}: 数据暂不可用")

    print("\n【风险】")
    print("- 数据源波动时部分内容会缺失；重大事件以交易所公告为准。")
    print("- 以上内容仅供复盘与风控，不构成投资建议。\n")


def _fetch_zt_pool_df() -> Optional["Any"]:
    # 涨停池：用于题材聚合/连板梯队
    import pandas as pd
    import akshare as ak

    date_str = pd.Timestamp.now().strftime("%Y%m%d")
    try:
        df = ak.stock_zt_pool_em(date=date_str)
        return df
    except Exception:
        return None


def _themes_from_zt_pool(df, top_n: int = 8) -> List[Dict[str, Any]]:
    # 尽可能适配字段名差异
    if df is None or getattr(df, "empty", True):
        return []

    cols = list(df.columns)
    streak_col = next((c for c in cols if "连板" in c), None)
    industry_col = next((c for c in cols if "行业" in c), None)
    concept_col = next((c for c in cols if "概念" in c or "题材" in c), None)

    # 主题优先：概念 > 行业
    theme_col = concept_col or industry_col
    if not theme_col:
        return []

    def _streak_val(x) -> int:
        try:
            v = int(x)
            return v if v > 0 else 1
        except Exception:
            return 1

    def _split_themes(raw: str) -> List[str]:
        text = str(raw or "").strip()
        if not text or text == "nan":
            return []
        parts = re.split(r"[;,，、/|]+", text)
        return [p.strip() for p in parts if p.strip()]

    agg: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        themes = _split_themes(row.get(theme_col, ""))
        if not themes:
            continue
        boards = _streak_val(row.get(streak_col, 1)) if streak_col else 1
        for theme in themes:
            a = agg.setdefault(
                theme,
                {"theme": theme, "count": 0, "boards_sum": 0, "max_boards": 1, "multi_boards": 0},
            )
            a["count"] += 1
            a["boards_sum"] += boards
            a["max_boards"] = max(a["max_boards"], boards)
            if boards >= 2:
                a["multi_boards"] += 1

    items = list(agg.values())
    # score: 数量 + 连板贡献 + 2板以上持续性
    for it in items:
        it["score"] = round(
            it["count"]
            + 0.4 * max(0, it["boards_sum"] - it["count"])
            + 0.8 * it["multi_boards"],
            2,
        )
    items.sort(key=lambda x: (x["score"], x["multi_boards"], x["max_boards"], x["count"]), reverse=True)
    return items[:top_n]


# ─────────────────────────────────────────────────────────────
# Alert de-dup
# ─────────────────────────────────────────────────────────────
def _dedup_key(kind: str, name: str) -> str:
    return f"{kind}:{name}"


def _seen_recent(key: str, ttl: int) -> bool:
    seen = _load_json(_alerts_seen_path(), {})
    ts = seen.get(key)
    if not ts:
        return False
    return (time.time() - float(ts)) < ttl


def _mark_seen(key: str) -> None:
    seen = _load_json(_alerts_seen_path(), {})
    seen[key] = time.time()
    _save_json(_alerts_seen_path(), seen)


# ─────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────
def _stance_from_stats(stats: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[str, str]:
    r = cfg["risk"]
    ratio = stats["ratio"]
    ld = stats["limit_down"]
    up = stats["limit_up"]
    down_gt5 = stats["down_gt5"]

    if ratio < r["breadth_ratio_weak"] or ld >= r["limit_down_risk"] or down_gt5 >= r["down_gt5_risk"]:
        return "防守", "弱势/风险偏好收缩：先控回撤，减少追涨试错"
    if ratio > r["breadth_ratio_strong"] and up >= r["limit_up_good"] and ld < r["limit_down_risk"]:
        return "进攻", "赚钱效应较好：可提高参与度，但仍分批与设止损"
    return "混沌", "结构不清晰：轻仓试错，等待主线与广度确认"


def morning_report() -> None:
    ensure_state_files()
    cfg = _load_json(_config_path(), _default_config())

    print("=" * 72)
    print(f"🦞 A股龙虾晨报（短线）  {_now_str()}")
    print("=" * 72)

    # Use last saved market stats if not in trading time; but we still pull snapshot
    try:
        df_spot = _get_all_spot_df()
        stats = _breadth_stats_from_spot(df_spot) if df_spot is not None and not df_spot.empty else {}
    except Exception:
        stats = {}

    idx_df = _index_quotes_df()

    stance, stance_note = _stance_from_stats(stats, cfg) if stats else ("混沌", "数据不足：先以防守心态")

    print("\nTL;DR")
    print(f"- 今日基调: **{stance}**；{stance_note}")

    print("\n证据")
    if idx_df is not None and not idx_df.empty:
        # print only key indices
        focus = ["上证指数", "深证成指", "创业板指", "科创50", "沪深300", "中证1000", "国证2000"]
        sub = idx_df[idx_df["指数"].isin(focus)].copy()
        for _, row in sub.iterrows():
            print(f"- {row['指数']}: {row['最新价']:.2f}  ({row['涨跌幅']:.2f}%)")
    if stats:
        print(f"- 广度: 上涨{stats['up']} / 下跌{stats['down']}  涨跌比={stats['ratio']:.2f}")
        print(f"- 涨跌停: 涨停{stats['limit_up']} / 跌停{stats['limit_down']}  跌幅>5%={stats['down_gt5']}")
    else:
        print("- 广度/涨跌停: 暂不可用（全市场快照接口波动，已自动跳过）")

    print("\n行动")
    if stance == "防守":
        print("- 仓位建议: **轻仓/降低试错频率**（优先保住回撤曲线）")
        print("- 只做两类: 强势主线的低风险节点 / 超跌反抽的快进快出（严格止损）")
    elif stance == "进攻":
        print("- 仓位建议: **可逐步提高参与度**（分批加仓，不一次满仓）")
        print("- 优先做: 有梯队与扩散的主线、强者恒强的趋势票")
    else:
        print("- 仓位建议: **轻仓试错**，等广度与主线确认再加仓")
        print("- 重点观察: 连板高度、涨停家数、跌停扩张是否缓和")

    print("\n风险（失效条件）")
    print("- 跌停数持续扩张 / 跌幅>5%家数高位不降 → 继续防守")
    print("- 主线无持续性（一天一个题材）→ 不追高，等待分歧转一致或确认点")

    _save_json(os.path.join(_REPORTS_DIR, f"morning_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"), {"stance": stance, "stats": stats})


def close_report() -> None:
    ensure_state_files()
    cfg = _load_json(_config_path(), _default_config())

    print("=" * 72)
    print(f"🦞 A股龙虾收盘复盘（短线）  {_now_str()}")
    print("=" * 72)

    try:
        df_spot = _get_all_spot_df()
        stats = _breadth_stats_from_spot(df_spot) if df_spot is not None and not df_spot.empty else {}
    except Exception:
        stats = {}
    idx_df = _index_quotes_df()
    zt_df = _fetch_zt_pool_df()
    themes = _themes_from_zt_pool(zt_df, top_n=int(cfg["report"]["top_theme_n"]))
    stance, stance_note = _stance_from_stats(stats, cfg) if stats else ("混沌", "广度/涨跌停数据不可用：以防守心态为主")

    print("\nTL;DR")
    print(f"- 今日复盘: **{stance}**；{stance_note}")

    print("\n证据")
    if idx_df is not None and not idx_df.empty:
        focus = ["上证指数", "创业板指", "科创50", "沪深300", "中证1000", "国证2000"]
        sub = idx_df[idx_df["指数"].isin(focus)].copy()
        for _, row in sub.iterrows():
            print(f"- {row['指数']}: {row['最新价']:.2f}  ({row['涨跌幅']:.2f}%)")
    if stats:
        print(f"- 广度: 上涨{stats['up']} / 下跌{stats['down']}  涨跌比={stats['ratio']:.2f}  市场均涨幅={stats['mean_pct']:.2f}%")
        print(f"- 涨跌停: 涨停{stats['limit_up']} / 跌停{stats['limit_down']}  涨幅>5%={stats['up_gt5']}  跌幅>5%={stats['down_gt5']}")
    else:
        print("- 广度/涨跌停: 暂不可用（全市场快照接口波动，已自动跳过）")

    print("\n题材（基于涨停池聚合）")
    if themes:
        for it in themes:
            print(
                f"- {it['theme']}: score={it['score']}  涨停={it['count']}  "
                f"2板+={it['multi_boards']}  最高连板={it['max_boards']}"
            )
    else:
        print("- 无法获取涨停池/题材数据（可能非交易时段或接口波动）")

    print("\n行动（明日）")
    if stance == "防守":
        print("- 明日策略: **控回撤为先**；只做最确定性节点，避免高位接力")
    elif stance == "进攻":
        print("- 明日策略: **围绕主线做强者恒强**；分歧敢低吸，转弱就走")
    else:
        print("- 明日策略: **轻仓试错**；等主线与广度给出一致信号")

    print("\n风险（明日关注）")
    print("- 跌停扩张、炸板增多、最高连板断板 → 情绪退潮信号")
    print("- 指数企稳但广度走弱 → 可能是假稳，谨慎加仓")

    last = _load_json(_market_last_path(), {})
    last.update({"ts": time.time(), "stats": stats, "stance": stance})
    _save_json(_market_last_path(), last)
    _save_json(os.path.join(_REPORTS_DIR, f"close_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"), {"stance": stance, "stats": stats, "themes": themes})


def scan_alerts() -> None:
    ensure_state_files()
    cfg = _load_json(_config_path(), _default_config())
    ttl = int(cfg["dedup_ttl_sec"])

    wl = _load_json(_watchlist_path(), {"stocks": [], "keywords": [], "blacklist": []})
    last = _load_json(_market_last_path(), {})

    try:
        df_spot = _get_all_spot_df()
    except Exception:
        df_spot = None

    stats = {}
    stance = "混沌"
    if df_spot is not None and not df_spot.empty:
        stats = _breadth_stats_from_spot(df_spot)
        stance, _ = _stance_from_stats(stats, cfg)

    alerts: List[Tuple[str, str, str]] = []  # (level, title, detail)
    r = cfg["risk"]

    # Compare with last snapshot (detect expansion/repair)
    last_stats = last.get("stats") if isinstance(last, dict) else None
    if stats and isinstance(last_stats, dict) and last_stats:
        try:
            ld_delta = int(stats["limit_down"]) - int(last_stats.get("limit_down", 0))
            lu_delta = int(stats["limit_up"]) - int(last_stats.get("limit_up", 0))
            ratio_delta = float(stats["ratio"]) - float(last_stats.get("ratio", 0))
            if ld_delta >= 5:
                alerts.append(("风险", "跌停扩张", f"跌停较上次 +{ld_delta}（{last_stats.get('limit_down')}→{stats['limit_down']}）"))
            if lu_delta >= 15 and ratio_delta > 0:
                alerts.append(("信息", "赚钱效应回暖", f"涨停较上次 +{lu_delta}，涨跌比+{ratio_delta:.2f}"))
            if ratio_delta <= -0.3 and stats["ratio"] < r["breadth_ratio_weak"]:
                alerts.append(("关注", "广度转弱", f"涨跌比较上次 {ratio_delta:.2f}（{last_stats.get('ratio'):.2f}→{stats['ratio']:.2f}）"))
        except Exception:
            pass

    # Risk alerts (only when breadth stats available)
    if stats:
        if stats["limit_down"] >= r["limit_down_risk"]:
            alerts.append(("风险", "跌停扩张", f"跌停={stats['limit_down']}（>= {r['limit_down_risk']}）"))
        if stats["ratio"] < r["breadth_ratio_weak"]:
            alerts.append(("关注", "广度偏弱", f"涨跌比={stats['ratio']:.2f}（< {r['breadth_ratio_weak']}）"))
        if stats["limit_up"] >= r["limit_up_good"] and stats["limit_down"] < r["limit_down_risk"]:
            alerts.append(("信息", "赚钱效应改善", f"涨停={stats['limit_up']}（>= {r['limit_up_good']}）且跌停={stats['limit_down']}"))

    # Watchlist stock alerts (simple)
    entries = _watchlist_entries(wl)
    blacklist = set(str(x) for x in (wl.get("blacklist") or []))
    stocks = [e["code"] for e in entries if e["code"] not in blacklist]
    if stats and stocks:
        for code in stocks:
            m = df_spot[df_spot["代码"] == code]
            if m.empty:
                continue
            row = m.iloc[0]
            name = row.get("名称", "")
            chg = row.get("涨跌幅")
            if chg is None:
                continue
            try:
                chg = float(chg)
            except Exception:
                continue
            if chg >= 5:
                alerts.append(("信息", "自选股拉升", f"{code} {name} 涨跌幅={chg:.2f}%"))
            if chg <= -5:
                alerts.append(("关注", "自选股走弱", f"{code} {name} 涨跌幅={chg:.2f}%"))

    # News / announcements keyword triggers (optional, resilient)
    try:
        news_cfg = cfg.get("news", {}) if isinstance(cfg, dict) else {}
        if news_cfg.get("enabled_in_scan", True):
            import akshare as ak

            kw_levels = news_cfg.get("keyword_level", {}) if isinstance(news_cfg.get("keyword_level", {}), dict) else {}
            watch_keywords = [str(x).strip() for x in wl.get("keywords", []) if str(x).strip()]
            ignore_terms = [str(x).strip() for x in news_cfg.get("ignore_terms", []) if str(x).strip()]
            flash_non_risk_require_watch_keyword = bool(news_cfg.get("flash_non_risk_require_watch_keyword", True))

            # Flash news
            flash_n = int(news_cfg.get("flash_count", 50))
            try:
                fdf = ak.stock_info_global_em()
                if fdf is not None and not fdf.empty:
                    for _, row in fdf.head(flash_n).iterrows():
                        content = ""
                        tstr = ""
                        for c in fdf.columns:
                            lc = str(c).lower()
                            if "时间" in str(c) or "date" in lc:
                                tstr = str(row.get(c, ""))[:19]
                            if "内容" in str(c) or "标题" in str(c) or "title" in lc:
                                content = str(row.get(c, ""))
                        lvl, hit_kw, is_watch_kw = _keyword_match_level(content, kw_levels, watch_keywords, ignore_terms)
                        if lvl:
                            if flash_non_risk_require_watch_keyword and lvl != "风险" and not is_watch_kw:
                                continue
                            alerts.append((lvl, "快讯命中关键词", f"[{tstr}] [{hit_kw}] {content[:120]}"))
            except Exception:
                pass

            # Stock announcements (watchlist)
            ann_n = int(news_cfg.get("announce_count_per_stock", 8))
            for code in stocks[: int(cfg.get("watchlist", {}).get("max_items", 50))]:
                try:
                    adf = ak.stock_notice_report(symbol=code)
                    if adf is None or adf.empty:
                        continue
                    for _, row in adf.head(ann_n).iterrows():
                        title = ""
                        d = ""
                        for c in adf.columns:
                            lc = str(c).lower()
                            if "日期" in str(c) or "时间" in str(c) or "date" in lc:
                                d = str(row.get(c, ""))[:10]
                            if "标题" in str(c) or "公告" in str(c) or "title" in lc:
                                title = str(row.get(c, ""))
                        lvl, hit_kw, _ = _keyword_match_level(title, kw_levels, watch_keywords, ignore_terms)
                        if lvl:
                            alerts.append((lvl, "自选股公告命中", f"{code} [{d}] [{hit_kw}] {title[:120]}"))
                except Exception:
                    continue
    except Exception:
        pass

    # De-dup and print
    out = []
    for level, title, detail in alerts:
        key = _dedup_key(level, title + "|" + detail.split("（")[0])
        if _seen_recent(key, ttl):
            continue
        _mark_seen(key)
        out.append((level, title, detail))

    print("=" * 72)
    print(f"🦞 盘中扫描（短线）  {_now_str()}  |  基调={stance}")
    print("=" * 72)
    if not out:
        print("暂无新告警（已去重）")
        return
    for level, title, detail in out:
        print(f"- [{level}] {title}: {detail}")

    # Persist latest snapshot for next delta detection (only if stats available)
    if stats:
        last = _load_json(_market_last_path(), {})
        last.update({"ts": time.time(), "stats": stats, "stance": stance})
        _save_json(_market_last_path(), last)


def watchlist_cmd(args: List[str]) -> None:
    ensure_state_files()
    wl = _load_json(_watchlist_path(), {"stocks": [], "keywords": [], "blacklist": []})

    def _save():
        _save_json(_watchlist_path(), wl)

    if not args or args[0] == "show":
        print(json.dumps(wl, ensure_ascii=False, indent=2))
        return

    if args[0] == "template":
        print(
            json.dumps(
                {
                    "stocks": [
                        {
                            "code": "600519",
                            "thesis": "为什么买它",
                            "buy_zone": "参考买入区间",
                            "stop_loss": "止损位/条件",
                            "invalid_if": "逻辑何时失效",
                            "target_days": 10,
                        }
                    ],
                    "keywords": ["回购", "增持"],
                    "blacklist": [],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    cmd = args[0]
    if cmd == "add-stock" and len(args) >= 2:
        code = args[1].strip()
        norm = _normalize_stock_code(code)
        entries = _watchlist_entries(wl)
        if norm and all(e["code"] != norm for e in entries):
            wl["stocks"].append(
                {
                    "code": norm,
                    "thesis": "",
                    "buy_zone": "",
                    "stop_loss": "",
                    "invalid_if": "",
                    "target_days": 10,
                }
            )
            _save()
        print("OK")
        return
    if cmd == "rm-stock" and len(args) >= 2:
        code = _normalize_stock_code(args[1].strip())
        kept = []
        for item in wl["stocks"]:
            if isinstance(item, dict):
                if _normalize_stock_code(str(item.get("code", ""))) != code:
                    kept.append(item)
            else:
                if _normalize_stock_code(str(item)) != code:
                    kept.append(item)
        wl["stocks"] = kept
        _save()
        print("OK")
        return
    if cmd == "set-field" and len(args) >= 4:
        code = _normalize_stock_code(args[1].strip())
        field = args[2].strip()
        value = " ".join(args[3:]).strip()
        allowed = {"thesis", "buy_zone", "stop_loss", "invalid_if", "target_days"}
        if field not in allowed:
            print(f"不支持字段: {field}，可用: {', '.join(sorted(allowed))}")
            sys.exit(1)
        changed = False
        new_items = []
        for item in wl["stocks"]:
            if isinstance(item, dict):
                obj = dict(item)
            else:
                obj = {
                    "code": _normalize_stock_code(str(item)),
                    "thesis": "",
                    "buy_zone": "",
                    "stop_loss": "",
                    "invalid_if": "",
                    "target_days": 10,
                }
            if obj.get("code") == code:
                obj[field] = int(value) if field == "target_days" and value.isdigit() else value
                changed = True
            new_items.append(obj)
        if not changed:
            print(f"未找到股票: {code}")
            sys.exit(1)
        wl["stocks"] = new_items
        _save()
        print("OK")
        return
    if cmd == "add-keyword" and len(args) >= 2:
        kw = args[1].strip()
        if kw and kw not in wl["keywords"]:
            wl["keywords"].append(kw)
            _save()
        print("OK")
        return
    if cmd == "rm-keyword" and len(args) >= 2:
        kw = args[1].strip()
        wl["keywords"] = [x for x in wl["keywords"] if x != kw]
        _save()
        print("OK")
        return

    print("未知 watchlist 命令。可用: show, template, add-stock, rm-stock, set-field, add-keyword, rm-keyword")
    sys.exit(1)


def main():
    ensure_state_files()
    if len(sys.argv) < 2:
        print("用法:")
        print("  python hub.py morning")
        print("  python hub.py scan")
        print("  python hub.py close")
        print("  python hub.py swing      # 波段(~2周)参谋简报")
        print("  python hub.py watchlist [show|template|add-stock|rm-stock|set-field|add-keyword|rm-keyword] ...")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "morning":
        morning_report()
    elif cmd == "scan":
        scan_alerts()
    elif cmd == "close":
        close_report()
    elif cmd == "swing":
        swing_advisor_brief()
    elif cmd == "watchlist":
        watchlist_cmd(sys.argv[2:])
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

