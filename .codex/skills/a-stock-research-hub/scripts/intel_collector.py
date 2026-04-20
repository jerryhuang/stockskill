#!/usr/bin/env python3
"""
情报采集模块 —— 为预测型分析提供前瞻性数据

采集维度:
1. 多日指数K线 (OHLC + 技术指标信号)
2. 财经快讯 (最近30条)
3. 全球财经日历 (当日即将公布的事件)
4. 行业板块主力资金流向 (板块轮动方向)
5. 昨日涨停溢价率 (情绪先行指标)
6. 市场异动信号 (大笔买卖、急速涨停)
7. 北向资金概况

所有函数返回 dict / list，不做 print，供 hub.py data_dump() 合并输出。
"""
from __future__ import annotations

import re
import sys
import os
import warnings
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../a-stock-shared/scripts"))


def _safe(fn, default=None):
    """执行函数，异常时返回默认值。"""
    try:
        return fn()
    except Exception as e:
        return {"error": str(e)[:200]} if default is None else default


# ═══════════════════════════════════════════════════════════
#  1. 多日指数K线 + 技术指标信号
# ═══════════════════════════════════════════════════════════
def _fetch_index_klines(symbol: str, n: int = 25) -> List[Dict]:
    """通过 akshare 获取指数最近 n 根日K线 OHLC 数据。"""
    import akshare as ak
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or df.empty:
            return []
        df = df.tail(n)
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "date": str(row["date"])[:10],
                "open": float(row["open"]),
                "close": float(row["close"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "volume": float(row["volume"]),
            })
        return rows
    except Exception:
        return []


def _compute_ma(closes: List[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)


def _compute_ema(closes: List[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return round(ema, 4)


def _compute_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def _compute_macd(closes: List[float]):
    if len(closes) < 26:
        return None, None, None
    ema12 = _compute_ema(closes, 12)
    ema26 = _compute_ema(closes, 26)
    if ema12 is None or ema26 is None:
        return None, None, None
    dif = round(ema12 - ema26, 4)
    difs = []
    e12, e26 = closes[0], closes[0]
    k12, k26 = 2 / 13, 2 / 27
    for c in closes[1:]:
        e12 = c * k12 + e12 * (1 - k12)
        e26 = c * k26 + e26 * (1 - k26)
        difs.append(e12 - e26)
    dea = difs[0]
    k9 = 2 / 10
    for d in difs[1:]:
        dea = d * k9 + dea * (1 - k9)
    dea = round(dea, 4)
    histogram = round(2 * (dif - dea), 4)
    return dif, dea, histogram


def collect_index_technicals(days: int = 40) -> Dict[str, Any]:
    """采集多指数多日K线并计算技术信号。"""
    indices = [
        ("sh000001", "上证指数"),
        ("sz399001", "深证成指"),
        ("sz399006", "创业板指"),
        ("sh000300", "沪深300"),
        ("sh000905", "中证500"),
    ]
    result = {}
    for symbol, name in indices:
        bars = _fetch_index_klines(symbol, n=days)
        if not bars:
            result[name] = {"error": "获取失败"}
            continue
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]

        ma5 = _compute_ma(closes, 5)
        ma10 = _compute_ma(closes, 10)
        ma20 = _compute_ma(closes, 20)
        rsi14 = _compute_rsi(closes, 14)
        dif, dea, hist = _compute_macd(closes)

        last = closes[-1]
        prev = closes[-2] if len(closes) > 1 else last
        chg_1d = round((last - prev) / prev * 100, 2) if prev else 0
        chg_3d = round((last - closes[-4]) / closes[-4] * 100, 2) if len(closes) >= 4 else None
        chg_5d = round((last - closes[-6]) / closes[-6] * 100, 2) if len(closes) >= 6 else None

        # MA 排列判断
        ma_alignment = "unknown"
        if ma5 and ma10 and ma20:
            if ma5 > ma10 > ma20:
                ma_alignment = "多头排列(bullish)"
            elif ma5 < ma10 < ma20:
                ma_alignment = "空头排列(bearish)"
            else:
                ma_alignment = "交织(mixed)"

        # MACD 方向
        macd_signal = "unknown"
        if hist is not None:
            if hist > 0:
                macd_signal = "多方放量" if dif and dif > dea else "多方缩量"
            else:
                macd_signal = "空方放量" if dif and dif < dea else "空方缩量"

        # RSI 区域
        rsi_zone = "unknown"
        if rsi14 is not None:
            if rsi14 >= 70:
                rsi_zone = "超买(overbought)"
            elif rsi14 <= 30:
                rsi_zone = "超卖(oversold)"
            elif rsi14 >= 55:
                rsi_zone = "偏强"
            elif rsi14 <= 45:
                rsi_zone = "偏弱"
            else:
                rsi_zone = "中性"

        # 支撑/压力位
        recent_high = max(highs[-10:]) if len(highs) >= 10 else max(highs)
        recent_low = min(lows[-10:]) if len(lows) >= 10 else min(lows)

        # 连涨/连跌天数
        streak = 0
        for i in range(len(closes) - 1, 0, -1):
            if closes[i] > closes[i - 1]:
                if streak >= 0:
                    streak += 1
                else:
                    break
            elif closes[i] < closes[i - 1]:
                if streak <= 0:
                    streak -= 1
                else:
                    break
            else:
                break

        result[name] = {
            "klines_recent5": bars[-5:],
            "close": last,
            "change_1d_pct": chg_1d,
            "change_3d_pct": chg_3d,
            "change_5d_pct": chg_5d,
            "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "ma_alignment": ma_alignment,
            "rsi14": rsi14, "rsi_zone": rsi_zone,
            "macd": {"dif": dif, "dea": dea, "histogram": hist, "signal": macd_signal},
            "support_10d": round(recent_low, 2),
            "resistance_10d": round(recent_high, 2),
            "consecutive_days": streak,
        }
        time.sleep(0.3)
    return result


# ═══════════════════════════════════════════════════════════
#  2. 财经快讯 (最近30条)
# ═══════════════════════════════════════════════════════════
def collect_flash_news(count: int = 30) -> List[Dict]:
    import akshare as ak
    rows = []
    try:
        df = ak.stock_info_global_em()
        if df is not None and not df.empty:
            for _, row in df.head(count).iterrows():
                item = {}
                for col in df.columns:
                    if "时间" in col or "date" in col.lower():
                        item["time"] = str(row[col])
                    elif "内容" in col or "title" in col.lower() or "标题" in col:
                        item["content"] = str(row[col])[:200]
                if item.get("content"):
                    rows.append(item)
    except Exception:
        pass
    return rows


# ═══════════════════════════════════════════════════════════
#  3. 全球财经日历
# ═══════════════════════════════════════════════════════════
def collect_economic_calendar() -> List[Dict]:
    import akshare as ak
    import pandas as pd
    rows = []
    try:
        df = ak.news_economic_baidu(date="today")
        if df is not None and not df.empty:
            for _, row in df.head(30).iterrows():
                item = {}
                for col in df.columns:
                    if "时间" in col:
                        item["time"] = str(row[col])
                    elif "国家" in col or "地区" in col:
                        item["country"] = str(row[col])
                    elif "事件" in col or "指标" in col:
                        item["event"] = str(row[col])[:80]
                    elif "重要性" in col or "星级" in col:
                        item["importance"] = str(row[col])
                    elif "前值" in col:
                        item["previous"] = str(row[col]) if pd.notna(row[col]) else ""
                    elif "预期" in col:
                        item["forecast"] = str(row[col]) if pd.notna(row[col]) else ""
                    elif "公布" in col:
                        item["actual"] = str(row[col]) if pd.notna(row[col]) else ""
                if item.get("event"):
                    rows.append(item)
    except Exception:
        pass
    return rows


# ═══════════════════════════════════════════════════════════
#  4. 行业板块主力资金流向 (板块轮动方向)
# ═══════════════════════════════════════════════════════════
def collect_sector_fund_flow(top_n: int = 15) -> Dict[str, Any]:
    import akshare as ak
    import pandas as pd
    inflows, outflows = [], []
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        if df is not None and not df.empty:
            net_col = next((c for c in df.columns if "主力净流入" in c and "净额" in c), None)
            pct_col = next((c for c in df.columns if "主力净" in c and "净占比" in c), None)
            name_col = next((c for c in df.columns if c == "名称"), None)
            chg_col = next((c for c in df.columns if "涨跌幅" in c), None)
            if not net_col or not name_col:
                return {"error": f"列名不匹配: {list(df.columns)}"}
            for i, row in df.iterrows():
                name = str(row[name_col])
                val = row[net_col]
                if pd.isna(val):
                    continue
                net_yi = round(float(val) / 1e8, 2) if abs(float(val)) > 1e6 else round(float(val), 2)
                item = {"rank": i + 1, "name": name, "net_inflow_yi": net_yi}
                if pct_col and pd.notna(row[pct_col]):
                    item["net_pct"] = round(float(row[pct_col]), 2)
                if chg_col and pd.notna(row[chg_col]):
                    item["change_pct"] = round(float(row[chg_col]), 2)
                if net_yi >= 0:
                    inflows.append(item)
                else:
                    outflows.append(item)
    except Exception as e:
        return {"error": str(e)[:200]}
    return {
        "top_inflow": inflows[:top_n],
        "top_outflow": sorted(outflows, key=lambda x: x["net_inflow_yi"])[:top_n],
        "summary": f"净流入{len(inflows)}个板块 / 净流出{len(outflows)}个板块",
    }


# ═══════════════════════════════════════════════════════════
#  5. 昨日涨停溢价率 (情绪先行指标)
# ═══════════════════════════════════════════════════════════
def collect_limit_up_premium() -> Dict[str, Any]:
    import akshare as ak
    import pandas as pd
    import numpy as np
    try:
        df = ak.stock_zt_pool_previous_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if df is None or df.empty:
            return {"status": "no_data"}

        pct_vals = []
        samples = []
        for _, row in df.iterrows():
            for col in df.columns:
                if "涨跌幅" in col:
                    val = row[col]
                    if pd.notna(val):
                        pct_vals.append(float(val))
            code_v = ""
            name_v = ""
            chg_v = None
            for col in df.columns:
                if "代码" in col:
                    code_v = str(row[col])
                elif "名称" in col:
                    name_v = str(row[col])[:8]
                elif "涨跌幅" in col and pd.notna(row[col]):
                    chg_v = round(float(row[col]), 2)
            if chg_v is not None and len(samples) < 10:
                samples.append({"code": code_v, "name": name_v, "today_pct": chg_v})

        if not pct_vals:
            return {"status": "no_data"}
        avg = round(np.mean(pct_vals), 2)
        median = round(np.median(pct_vals), 2)
        pos = sum(1 for v in pct_vals if v > 0)
        neg = len(pct_vals) - pos

        emotion = "强势" if avg > 2 else "正常" if avg > 0 else "弱势" if avg > -2 else "冰点"
        return {
            "total": len(pct_vals),
            "avg_premium_pct": avg,
            "median_premium_pct": median,
            "up_count": pos,
            "down_count": neg,
            "emotion_signal": emotion,
            "interpretation": (
                f"昨日{len(pct_vals)}只涨停股今日平均溢价{avg}%，"
                f"{'赚钱效应延续' if avg > 1 else '分歧加大' if avg > -1 else '亏钱效应蔓延'}，"
                f"{'短线情绪向好' if emotion in ('强势', '正常') else '短线风险加大'}"
            ),
            "top_samples": samples,
        }
    except Exception as e:
        return {"error": str(e)[:200]}


# ═══════════════════════════════════════════════════════════
#  6. 市场异动信号
# ═══════════════════════════════════════════════════════════
def collect_unusual_activity() -> Dict[str, List]:
    import akshare as ak
    import pandas as pd
    result = {}
    for label, symbol in [("大笔买入", "大笔买入"), ("急速涨停", "急速涨停"), ("大笔卖出", "大笔卖出")]:
        items = []
        try:
            df = ak.stock_changes_em(symbol=symbol)
            if df is not None and not df.empty:
                for _, row in df.head(10).iterrows():
                    item = {}
                    for col in df.columns:
                        if "代码" in col:
                            item["code"] = str(row[col])
                        elif "名称" in col:
                            item["name"] = str(row[col])[:8]
                        elif "涨跌幅" in col:
                            item["change_pct"] = round(float(row[col]), 2) if pd.notna(row[col]) else 0
                    if item.get("code"):
                        items.append(item)
        except Exception:
            pass
        result[label] = items
    return result


# ═══════════════════════════════════════════════════════════
#  7. 北向资金概况
# ═══════════════════════════════════════════════════════════
def collect_northbound_summary() -> Dict[str, Any]:
    import akshare as ak
    import pandas as pd
    result = {"note": "2024年8月起北向资金成交净买额不再实时披露"}
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is not None and not df.empty:
            rows = []
            for _, row in df.iterrows():
                item = {}
                for col in df.columns:
                    if "资金方向" in col:
                        item["direction"] = str(row[col])
                    elif "板块" in col:
                        item["board"] = str(row[col])
                    elif "成交净买额" in col:
                        item["net_buy_yi"] = round(float(row[col]), 2) if pd.notna(row[col]) else None
                    elif "指数涨跌幅" in col:
                        item["index_pct"] = round(float(row[col]), 2) if pd.notna(row[col]) else 0
                rows.append(item)
            result["flows"] = rows
    except Exception as e:
        result["error"] = str(e)[:200]
    return result


# ═══════════════════════════════════════════════════════════
#  8. 连板梯队详情 (高度生态)
# ═══════════════════════════════════════════════════════════
def collect_streak_ladder() -> Dict[str, Any]:
    import akshare as ak
    import pandas as pd
    try:
        df = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if df is None or df.empty:
            return {"status": "no_data"}
        streak_col = next((c for c in df.columns if "连板" in c), None)
        if not streak_col:
            return {"status": "no_streak_col"}

        ladder = {}
        for _, row in df.iterrows():
            boards = int(row[streak_col]) if pd.notna(row[streak_col]) else 1
            if boards < 2:
                continue
            code, name = "", ""
            for col in df.columns:
                if "代码" in col:
                    code = str(row[col])
                elif "名称" in col:
                    name = str(row[col])[:8]
            key = f"{boards}板"
            ladder.setdefault(key, []).append({"code": code, "name": name})

        max_height = max((int(row[streak_col]) for _, row in df.iterrows() if pd.notna(row[streak_col])), default=1)
        total_multi = sum(len(v) for v in ladder.values())
        return {
            "max_height": max_height,
            "multi_board_count": total_multi,
            "ladder": ladder,
            "health": (
                "梯队健康" if total_multi >= 8 and max_height >= 4
                else "梯队一般" if total_multi >= 4
                else "梯队断裂"
            ),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


# ═══════════════════════════════════════════════════════════
#  主入口: 一次性采集全部情报
# ═══════════════════════════════════════════════════════════
def collect_all_intel() -> Dict[str, Any]:
    """采集全部前瞻性情报数据，返回结构化 dict。
    使用并行采集 + 超时保护，总耗时控制在 120 秒内。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    intel = {"collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    tasks = {
        "index_technicals": (lambda: collect_index_technicals(40), {}),
        "flash_news": (lambda: collect_flash_news(30), []),
        "limit_up_premium": (lambda: collect_limit_up_premium(), {}),
        "streak_ladder": (lambda: collect_streak_ladder(), {}),
        "sector_fund_flow": (lambda: collect_sector_fund_flow(15), {}),
        "economic_calendar": (lambda: collect_economic_calendar(), []),
        "unusual_activity": (lambda: collect_unusual_activity(), {}),
        "northbound": (lambda: collect_northbound_summary(), {}),
    }

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for key, (fn, default) in tasks.items():
            futures[pool.submit(_safe, fn, default)] = key

        for future in as_completed(futures, timeout=120):
            key = futures[future]
            try:
                intel[key] = future.result(timeout=0)
            except Exception as e:
                intel[key] = {"error": str(e)[:200]}

    for key in tasks:
        if key not in intel:
            intel[key] = {"error": "超时跳过"}

    return intel


if __name__ == "__main__":
    import json
    print(json.dumps(collect_all_intel(), ensure_ascii=False, indent=2))
