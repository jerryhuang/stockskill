#!/usr/bin/env python3
"""A股个股监控与技术分析 - 使用共享快速API"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
from fast_api import get_all_a_stock_spot

import akshare as ak
import pandas as pd
import numpy as np
from tabulate import tabulate

pd.set_option("display.unicode.ambiguous_as_wide", True)
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)


def normalize_code(code: str) -> str:
    code = code.strip()
    for prefix in ["sh", "sz", "bj", "SH", "SZ", "BJ"]:
        if code.startswith(prefix):
            code = code[2:]
    return code


def get_quote(codes: str):
    """获取个股实时行情"""
    code_list = [normalize_code(c) for c in codes.split(",")]

    print("=" * 70)
    print("📊 个股实时行情")
    print("=" * 70)

    try:
        df = get_all_a_stock_spot()
        if df.empty:
            print("  未获取到数据")
            return

        rows = []
        for code in code_list:
            match = df[df["代码"] == code]
            if match.empty:
                print(f"  未找到股票: {code}")
                continue
            row = match.iloc[0]
            r = {
                "代码": row["代码"],
                "名称": row["名称"],
                "最新价": f"{row['最新价']:.2f}" if pd.notna(row["最新价"]) else "N/A",
                "涨跌幅%": f"{row['涨跌幅']:.2f}" if pd.notna(row["涨跌幅"]) else "N/A",
                "成交量(万手)": f"{row['成交量']/10000:.1f}" if pd.notna(row["成交量"]) else "N/A",
                "成交额(亿)": f"{row['成交额']/1e8:.2f}" if pd.notna(row["成交额"]) else "N/A",
                "换手率%": f"{row['换手率']:.2f}" if pd.notna(row["换手率"]) else "N/A",
                "振幅%": f"{row['振幅']:.2f}" if pd.notna(row["振幅"]) else "N/A",
                "今开": f"{row['今开']:.2f}" if pd.notna(row["今开"]) else "N/A",
                "最高": f"{row['最高']:.2f}" if pd.notna(row["最高"]) else "N/A",
                "最低": f"{row['最低']:.2f}" if pd.notna(row["最低"]) else "N/A",
                "PE(动)": f"{row['市盈率']:.1f}" if pd.notna(row["市盈率"]) else "N/A",
                "总市值(亿)": f"{row['总市值']/1e8:.1f}" if pd.notna(row["总市值"]) else "N/A",
            }
            rows.append(r)

        if rows:
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        print()
    except Exception as e:
        print(f"  获取行情失败: {e}")


def get_kline(code: str, period: str = "daily", days: int = 60):
    """获取K线数据"""
    code = normalize_code(code)
    print("=" * 70)
    print(f"📈 K线数据 [{code}] 周期={period} 最近{days}条")
    print("=" * 70)

    try:
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        if df is None or df.empty:
            print("  未获取到数据")
            return

        df = df.tail(days)
        display_cols = [c for c in df.columns if any(k in c for k in ["日期", "开盘", "收盘", "最高", "最低", "成交量", "涨跌幅"])]
        if display_cols:
            print(tabulate(df[display_cols].tail(20), headers="keys", tablefmt="simple",
                           showindex=False, stralign="right"))
            if len(df) > 20:
                print(f"\n  (仅显示最近20条，共{len(df)}条)")
        print()
    except Exception as e:
        print(f"  获取K线失败: {e}")


def tech_analysis(code: str):
    """技术指标分析"""
    code = normalize_code(code)
    print("=" * 70)
    print(f"🔧 技术指标分析 [{code}]")
    print("=" * 70)

    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df is None or df.empty:
            print("  未获取到数据")
            return

        close_col = high_col = low_col = None
        for col in df.columns:
            if "收盘" in col: close_col = col
            elif "最高" in col: high_col = col
            elif "最低" in col: low_col = col

        if not all([close_col, high_col, low_col]):
            print("  数据列缺失")
            return

        close = df[close_col].astype(float)
        high = df[high_col].astype(float)
        low = df[low_col].astype(float)
        latest = close.iloc[-1]

        name_col = next((c for c in df.columns if "股票名称" in c or "名称" in c), None)
        stock_name = df[name_col].iloc[-1] if name_col else code

        print(f"\n  股票: {stock_name} ({code})  最新收盘价: {latest:.2f}\n")

        # MA
        print("  【均线系统 MA】")
        for period in [5, 10, 20, 60, 120, 250]:
            if len(close) >= period:
                ma = close.rolling(window=period).mean().iloc[-1]
                diff_pct = (latest - ma) / ma * 100
                status = "在上方 ↑" if latest > ma else "在下方 ↓"
                print(f"    MA{period}: {ma:.2f}  当前价{status} ({diff_pct:+.2f}%)")

        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        if len(ma5) > 1 and len(ma20) > 1:
            if ma5.iloc[-1] > ma20.iloc[-1] and ma5.iloc[-2] <= ma20.iloc[-2]:
                print("    ⚡ MA5上穿MA20，短期金叉！")
            elif ma5.iloc[-1] < ma20.iloc[-1] and ma5.iloc[-2] >= ma20.iloc[-2]:
                print("    ⚡ MA5下穿MA20，短期死叉！")

        # MACD
        print("\n  【MACD】")
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=9, adjust=False).mean()
        macd = 2 * (dif - dea)
        print(f"    DIF: {dif.iloc[-1]:.3f}  DEA: {dea.iloc[-1]:.3f}  MACD: {macd.iloc[-1]:.3f}")
        if dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-2] <= dea.iloc[-2]:
            print("    ⚡ MACD金叉！DIF上穿DEA")
        elif dif.iloc[-1] < dea.iloc[-1] and dif.iloc[-2] >= dea.iloc[-2]:
            print("    ⚡ MACD死叉！DIF下穿DEA")
        elif dif.iloc[-1] > dea.iloc[-1]:
            print("    多头排列（DIF > DEA）")
        else:
            print("    空头排列（DIF < DEA）")

        # KDJ
        print("\n  【KDJ】")
        lowest = low.rolling(9).min()
        highest = high.rolling(9).max()
        rsv = (close - lowest) / (highest - lowest) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d
        print(f"    K: {k.iloc[-1]:.2f}  D: {d.iloc[-1]:.2f}  J: {j.iloc[-1]:.2f}")
        if j.iloc[-1] < 20:
            print("    ⚡ J值低于20，超卖区域")
        elif j.iloc[-1] > 80:
            print("    ⚡ J值高于80，超买区域")
        if k.iloc[-1] > d.iloc[-1] and k.iloc[-2] <= d.iloc[-2]:
            print("    ⚡ KDJ金叉！K上穿D")
        elif k.iloc[-1] < d.iloc[-1] and k.iloc[-2] >= d.iloc[-2]:
            print("    ⚡ KDJ死叉！K下穿D")

        # RSI
        print("\n  【RSI】")
        for period in [6, 12, 24]:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(period).mean()
            loss = (-delta).where(delta < 0, 0).rolling(period).mean()
            rsi = 100 - (100 / (1 + gain / loss))
            val = rsi.iloc[-1]
            status = "超买⚠️" if val > 70 else ("超卖⚠️" if val < 30 else "正常")
            print(f"    RSI{period}: {val:.2f}  {status}")

        # BOLL
        print("\n  【布林带 BOLL】")
        ma20_val = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = ma20_val + 2 * std20
        lower = ma20_val - 2 * std20
        print(f"    上轨: {upper.iloc[-1]:.2f}  中轨: {ma20_val.iloc[-1]:.2f}  下轨: {lower.iloc[-1]:.2f}")
        if latest >= upper.iloc[-1]:
            print("    ⚡ 价格触及上轨，注意回调风险")
        elif latest <= lower.iloc[-1]:
            print("    ⚡ 价格触及下轨，关注反弹机会")
        else:
            width = (upper.iloc[-1] - lower.iloc[-1]) / ma20_val.iloc[-1] * 100
            print(f"    带宽: {width:.2f}%  价格在通道内运行")
        print()
    except Exception as e:
        print(f"  技术分析失败: {e}")


def search_stock(keyword: str):
    """搜索股票"""
    print("=" * 60)
    print(f"🔍 搜索: {keyword}")
    print("=" * 60)

    try:
        df = get_all_a_stock_spot()
        if df.empty:
            print("  无法获取数据")
            return

        mask = df["名称"].str.contains(keyword, na=False) | df["代码"].str.contains(keyword, na=False)
        results = df[mask]

        if results.empty:
            print(f"  未找到匹配 '{keyword}' 的股票")
            return

        rows = []
        for _, row in results.head(20).iterrows():
            rows.append({
                "代码": row["代码"],
                "名称": row["名称"],
                "最新价": f"{row['最新价']:.2f}" if pd.notna(row["最新价"]) else "N/A",
                "涨跌幅%": f"{row['涨跌幅']:.2f}" if pd.notna(row["涨跌幅"]) else "N/A",
            })

        print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        print()
    except Exception as e:
        print(f"  搜索失败: {e}")


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python stock_monitor.py quote 600519[,000858,...]")
        print("  python stock_monitor.py kline 600519 [daily|weekly|monthly] [天数]")
        print("  python stock_monitor.py tech 600519")
        print("  python stock_monitor.py search 贵州茅台")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "quote":
        if len(sys.argv) < 3:
            print("请提供股票代码"); sys.exit(1)
        get_quote(sys.argv[2])
    elif cmd == "kline":
        if len(sys.argv) < 3:
            print("请提供股票代码"); sys.exit(1)
        period = sys.argv[3] if len(sys.argv) > 3 else "daily"
        days = int(sys.argv[4]) if len(sys.argv) > 4 else 60
        get_kline(sys.argv[2], period, days)
    elif cmd == "tech":
        if len(sys.argv) < 3:
            print("请提供股票代码"); sys.exit(1)
        tech_analysis(sys.argv[2])
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("请提供搜索关键词"); sys.exit(1)
        search_stock(sys.argv[2])
    else:
        print(f"未知命令: {cmd}"); sys.exit(1)


if __name__ == "__main__":
    main()
