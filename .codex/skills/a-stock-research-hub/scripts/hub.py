#!/usr/bin/env python3
"""
短线投研编排中枢（云端可跑）：
- 生成晨报/盘中扫描/收盘复盘
- watchlist + 新闻关键词触发
- 告警去重（TTL）
"""

from __future__ import annotations

import json
import os
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
    tmp = path + ".tmp"
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
            "keyword_level": {
                "风险": ["立案", "处罚", "监管处罚", "退市", "终止上市", "ST", "风险提示", "诉讼", "仲裁"],
                "关注": ["减持", "质押", "解禁", "问询函", "关注函", "延期", "终止", "变更", "亏损"],
                "信息": ["回购", "增持", "业绩预告", "预增", "中标", "签订", "重大合同", "分红"],
            },
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
        _save_json(cfg_path, merged)

    wl_path = _watchlist_path()
    if not os.path.exists(wl_path):
        _save_json(
            wl_path,
            {
                "stocks": ["600519"],
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

    agg: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        theme = str(row.get(theme_col, "")).strip()
        if not theme or theme == "nan":
            continue
        boards = _streak_val(row.get(streak_col, 1)) if streak_col else 1
        a = agg.setdefault(theme, {"theme": theme, "count": 0, "boards_sum": 0, "max_boards": 1})
        a["count"] += 1
        a["boards_sum"] += boards
        a["max_boards"] = max(a["max_boards"], boards)

    items = list(agg.values())
    # score: 数量 + (连板贡献)
    for it in items:
        it["score"] = round(it["count"] + 0.6 * max(0, it["boards_sum"] - it["count"]), 2)
    items.sort(key=lambda x: (x["score"], x["max_boards"], x["count"]), reverse=True)
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
            print(f"- {it['theme']}: score={it['score']}  涨停={it['count']}  最高连板={it['max_boards']}")
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
    stocks = [s for s in wl.get("stocks", []) if s and s not in set(wl.get("blacklist", []))]
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
            import pandas as pd

            kw_levels = news_cfg.get("keyword_level", {}) if isinstance(news_cfg.get("keyword_level", {}), dict) else {}
            # user watchlist keywords also treated as "关注"
            watch_keywords = [str(x).strip() for x in wl.get("keywords", []) if str(x).strip()]

            def classify(text: str) -> Optional[str]:
                t = text or ""
                for lvl in ["风险", "关注", "信息"]:
                    for kw in kw_levels.get(lvl, []) or []:
                        if kw and kw in t:
                            return lvl
                for kw in watch_keywords:
                    if kw and kw in t:
                        return "关注"
                return None

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
                        lvl = classify(content)
                        if lvl:
                            alerts.append((lvl, "快讯命中关键词", f"[{tstr}] {content[:120]}"))
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
                        lvl = classify(title)
                        if lvl:
                            alerts.append((lvl, "自选股公告命中", f"{code} [{d}] {title[:120]}"))
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

    cmd = args[0]
    if cmd == "add-stock" and len(args) >= 2:
        code = args[1].strip()
        if code and code not in wl["stocks"]:
            wl["stocks"].append(code)
            _save()
        print("OK")
        return
    if cmd == "rm-stock" and len(args) >= 2:
        code = args[1].strip()
        wl["stocks"] = [x for x in wl["stocks"] if x != code]
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

    print("未知 watchlist 命令。可用: show, add-stock, rm-stock, add-keyword, rm-keyword")
    sys.exit(1)


def main():
    ensure_state_files()
    if len(sys.argv) < 2:
        print("用法:")
        print("  python hub.py morning")
        print("  python hub.py scan")
        print("  python hub.py close")
        print("  python hub.py watchlist [show|add-stock|rm-stock|add-keyword|rm-keyword] ...")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "morning":
        morning_report()
    elif cmd == "scan":
        scan_alerts()
    elif cmd == "close":
        close_report()
    elif cmd == "watchlist":
        watchlist_cmd(sys.argv[2:])
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

