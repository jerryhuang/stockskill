#!/usr/bin/env python3
"""A股资金流向数据获取 - 修复版（适配2024年8月后北向数据停披规则）"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../a-stock-shared/scripts"))
from fast_api import get_stock_individual_fund_flow

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


def get_north_flow():
    """北向资金今日概览"""
    print("=" * 70)
    print("💰 北向资金今日概览")
    print("=" * 70)
    print("  ⚠️  注：2024年8月起，北向资金成交净买额不再实时披露")
    print("      以下为可获取的跨境交易摘要与持股变动数据\n")

    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is not None and not df.empty:
            rows = []
            for _, row in df.iterrows():
                direction = row.get("资金方向", "")
                board = row.get("板块", "")
                net = row.get("成交净买额", 0)
                inflow = row.get("资金净流入", 0)
                idx = row.get("相关指数", "")
                idx_pct = row.get("指数涨跌幅", 0)
                up_n = row.get("上涨数", 0)
                down_n = row.get("下跌数", 0)
                status_code = row.get("交易状态", "")
                status = "交易中" if status_code == 3 else ("已收盘" if status_code == 1 else str(status_code))

                rows.append({
                    "方向": direction,
                    "板块": board,
                    "净买额(亿)": f"{net:.2f}" if pd.notna(net) else "-",
                    "状态": status,
                    "相关指数": f"{idx} {idx_pct:+.2f}%",
                    "涨/跌": f"{up_n}/{down_n}",
                })
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        print(f"  获取今日概览失败: {e}")
    print()


def get_north_hold(market: str = "all"):
    """北向资金持股排行（最新可用数据）"""
    print("=" * 70)
    print("📊 北向资金持股排行")
    print("=" * 70)

    markets = []
    if market == "all":
        markets = [("沪股通", "5日排行"), ("深股通", "5日排行")]
    elif market in ("sh", "沪股通"):
        markets = [("沪股通", "5日排行")]
    elif market in ("sz", "深股通"):
        markets = [("深股通", "5日排行")]

    for mkt, indicator in markets:
        print(f"\n  【{mkt} - {indicator}】")
        try:
            df = ak.stock_hsgt_hold_stock_em(market=mkt, indicator=indicator)
            if df is not None and not df.empty:
                date_col = next((c for c in df.columns if "日期" in c), None)
                if date_col:
                    latest_date = df[date_col].iloc[0]
                    print(f"  数据日期: {latest_date}")

                rows = []
                for _, row in df.head(15).iterrows():
                    r = {}
                    for col in df.columns:
                        if col == "代码":
                            r["代码"] = row[col]
                        elif col == "名称":
                            r["名称"] = str(row[col])[:8]
                        elif col == "今日收盘价":
                            r["收盘价"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                        elif col == "今日涨跌幅":
                            r["涨跌幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                        elif "持股-市值" in col and "估计" not in col:
                            val = row[col]
                            r["持股市值(亿)"] = f"{val/1e4:.2f}" if pd.notna(val) else ""
                        elif "占流通股比" in col and "估计" not in col:
                            r["占流通股%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                        elif "5日增持估计-市值" == col:
                            val = row[col]
                            r["5日增持(万)"] = f"{val:.0f}" if pd.notna(val) else ""
                        elif "5日增持估计-市值增幅" == col:
                            r["增持幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                        elif col == "所属板块":
                            r["板块"] = str(row[col])[:8] if pd.notna(row[col]) else ""
                    rows.append(r)

                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
            else:
                print("  未获取到数据")
        except Exception as e:
            print(f"  获取失败: {e}")
    print()


def get_north_board():
    """北向资金行业板块增持排行"""
    print("=" * 70)
    print("📈 北向资金行业板块增持排行")
    print("=" * 70)

    try:
        df = ak.stock_hsgt_board_rank_em(
            symbol="北向资金增持行业板块排行", indicator="今日"
        )
        if df is not None and not df.empty:
            date_col = next((c for c in df.columns if "时间" in c or "日期" in c), None)
            if date_col:
                print(f"  数据日期: {df[date_col].iloc[0]}")

            rows = []
            for _, row in df.head(20).iterrows():
                r = {}
                for col in df.columns:
                    if col == "名称":
                        r["行业"] = row[col]
                    elif col == "最新涨跌幅":
                        r["涨跌幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                    elif "持股-股票只数" in col:
                        r["持股数"] = int(row[col]) if pd.notna(row[col]) else ""
                    elif "持股-市值" in col and "估计" not in col:
                        val = row[col]
                        r["持股市值(亿)"] = f"{val/1e8:.1f}" if pd.notna(val) else ""
                    elif "增持估计-市值增幅" in col:
                        r["增持幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                    elif "增持最大股-市值" in col:
                        r["增持最大股"] = str(row[col])[:8] if pd.notna(row[col]) else ""
                rows.append(r)

            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  未获取到数据")
    except Exception as e:
        print(f"  获取失败: {e}")
    print()


def get_sector_flow():
    """行业板块主力资金流向"""
    print("=" * 70)
    print("📊 行业板块主力资金流向排名")
    print("=" * 70)

    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        if df is not None and not df.empty:
            rows = []
            for i, row in df.head(30).iterrows():
                r = {"排名": i + 1}
                for col in df.columns:
                    if "名称" in col:
                        r["板块"] = row[col]
                    elif "主力净流入" in col and "净占比" not in col:
                        val = row[col]
                        if pd.notna(val):
                            r["主力净流入(亿)"] = f"{val/1e8:.2f}" if abs(val) > 1e6 else f"{val:.2f}"
                        else:
                            r["主力净流入(亿)"] = "N/A"
                    elif "主力净占比" in col or "主力净流入-净占比" in col:
                        r["净占比%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else "N/A"
                rows.append(r)
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  未获取到数据")
    except Exception as e:
        print(f"  获取板块资金流向失败: {e}")
    print()


def get_top_flow():
    """个股主力资金排行"""
    print("=" * 70)
    print("🔝 个股主力资金净流入 Top 30")
    print("=" * 70)

    try:
        df = ak.stock_individual_fund_flow_rank(indicator="今日排行")
        if df is not None and not df.empty:
            rows = []
            for i, row in df.head(30).iterrows():
                r = {"排名": i + 1}
                for col in df.columns:
                    if "代码" in col:
                        r["代码"] = row[col]
                    elif "名称" in col:
                        r["名称"] = row[col]
                    elif "最新价" in col:
                        r["最新价"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                    elif "涨跌幅" in col:
                        r["涨跌幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                    elif "主力净流入" in col and "净占比" not in col:
                        val = row[col]
                        if pd.notna(val):
                            r["主力净流入(亿)"] = f"{val/1e8:.2f}" if abs(val) > 1e6 else f"{val:.2f}"
                        else:
                            r["主力净流入(亿)"] = ""
                rows.append(r)
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  未获取到数据")
    except Exception as e:
        print(f"  获取数据失败: {e}")
    print()


def get_stock_flow(code: str):
    """个股资金流向明细"""
    code = normalize_code(code)
    print("=" * 70)
    print(f"💹 个股资金流向 [{code}]（最近30日）")
    print("=" * 70)

    try:
        df = get_stock_individual_fund_flow(code)
        if df.empty:
            print("  未获取到数据")
            return

        recent = df.tail(10)
        rows = []
        for _, row in recent.iterrows():
            rows.append({
                "日期": row["日期"],
                "主力净流入(万)": f"{row['主力净流入']/1e4:.1f}",
                "大单(万)": f"{row['大单净流入']/1e4:.1f}",
                "超大单(万)": f"{row['超大单净流入']/1e4:.1f}",
                "中单(万)": f"{row['中单净流入']/1e4:.1f}",
                "小单(万)": f"{row['小单净流入']/1e4:.1f}",
            })
        print("\n  最近10日:")
        print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))

        total_main = df["主力净流入"].sum()
        pos_days = len(df[df["主力净流入"] > 0])
        print(f"\n  30日主力合计: {total_main/1e4:.1f}万  流入{pos_days}天/流出{len(df)-pos_days}天")
    except Exception as e:
        print(f"  获取失败: {e}")
    print()


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python capital_flow.py north              # 北向资金今日概览")
        print("  python capital_flow.py north-hold [all|sh|sz]  # 北向持股排行")
        print("  python capital_flow.py north-board        # 北向行业增持排行")
        print("  python capital_flow.py sector-flow        # 板块主力资金流向")
        print("  python capital_flow.py top-flow           # 个股主力资金排行")
        print("  python capital_flow.py stock-flow 600519  # 个股资金明细")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "north":
        get_north_flow()
    elif cmd == "north-hold":
        market = sys.argv[2] if len(sys.argv) > 2 else "all"
        get_north_hold(market)
    elif cmd == "north-board":
        get_north_board()
    elif cmd == "north-hist":
        print("⚠️  北向资金历史净买额自2024年8月起不再披露。")
        print("   请使用 north-hold 或 north-board 查看持股变动数据。")
    elif cmd == "sector-flow":
        get_sector_flow()
    elif cmd == "top-flow":
        get_top_flow()
    elif cmd == "stock-flow":
        if len(sys.argv) < 3:
            print("请提供股票代码"); sys.exit(1)
        get_stock_flow(sys.argv[2])
    else:
        print(f"未知命令: {cmd}"); sys.exit(1)


if __name__ == "__main__":
    main()
