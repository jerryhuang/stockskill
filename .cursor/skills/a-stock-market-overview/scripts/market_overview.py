#!/usr/bin/env python3
"""A股大盘概览数据获取 - 使用共享快速API"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
from fast_api import get_index_quotes, get_all_a_stock_spot

import pandas as pd
from tabulate import tabulate

pd.set_option("display.unicode.ambiguous_as_wide", True)
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)


def show_index():
    """主要指数行情"""
    print("=" * 60)
    print("📊 A股主要指数行情")
    print("=" * 60)

    try:
        df = get_index_quotes()
        if df.empty:
            print("  未获取到数据")
            return
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "指数": row["指数"],
                "最新价": f"{row['最新价']:.2f}",
                "涨跌幅%": f"{row['涨跌幅']:.2f}",
                "涨跌额": f"{row['涨跌额']:.2f}",
                "成交额(亿)": f"{row['成交额']/1e8:.1f}" if pd.notna(row["成交额"]) else "N/A",
            })
        print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        print(f"  获取指数失败: {e}")
    print()


def show_sector():
    """行业板块涨跌排名"""
    print("=" * 60)
    print("📈 行业板块涨跌排名")
    print("=" * 60)

    import akshare as ak
    try:
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            cols = {}
            for col in df.columns:
                if "板块名称" in col or "名称" in col:
                    cols["名称"] = col
                elif "涨跌幅" in col:
                    cols["涨跌幅"] = col
                elif "领涨股票" in col or "领涨" in col:
                    cols["领涨"] = col

            rows = []
            for i, row in df.head(31).iterrows():
                r = {"排名": i + 1, "板块": row.get(cols.get("名称", ""), "")}
                pct = row.get(cols.get("涨跌幅", ""), 0)
                r["涨跌幅%"] = f"{pct:.2f}" if pd.notna(pct) else "N/A"
                if "领涨" in cols:
                    r["领涨股"] = row.get(cols["领涨"], "")
                rows.append(r)
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  未获取到数据")
    except Exception as e:
        print(f"  获取板块失败: {e}")
    print()


def show_concept():
    """概念板块热度"""
    print("=" * 60)
    print("🔥 概念板块热度 Top 20")
    print("=" * 60)

    import akshare as ak
    try:
        df = ak.stock_board_concept_name_em()
        if df is not None and not df.empty:
            cols = {}
            for col in df.columns:
                if "板块名称" in col or "名称" in col:
                    cols["名称"] = col
                elif "涨跌幅" in col:
                    cols["涨跌幅"] = col

            rows = []
            for i, row in df.head(20).iterrows():
                r = {"排名": i + 1, "概念": row.get(cols.get("名称", ""), "")}
                pct = row.get(cols.get("涨跌幅", ""), 0)
                r["涨跌幅%"] = f"{pct:.2f}" if pd.notna(pct) else "N/A"
                rows.append(r)
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  未获取到数据")
    except Exception as e:
        print(f"  获取概念失败: {e}")
    print()


def show_breadth():
    """涨跌家数统计"""
    print("=" * 60)
    print("📊 全市场涨跌统计")
    print("=" * 60)

    try:
        df = get_all_a_stock_spot()
        if df.empty:
            print("  未获取到数据")
            return

        valid = df[pd.notna(df["涨跌幅"])].copy()
        total = len(valid)
        pct = valid["涨跌幅"]

        limit_up = len(pct[pct >= 9.9])
        limit_down = len(pct[pct <= -9.9])
        up = len(pct[pct > 0])
        down = len(pct[pct < 0])
        flat = len(pct[pct == 0])
        up_gt5 = len(pct[pct >= 5])
        down_gt5 = len(pct[pct <= -5])

        print(f"  总股票数:   {total}")
        print(f"  涨停:       {limit_up}")
        print(f"  跌停:       {limit_down}")
        print(f"  上涨:       {up}  ({up/total*100:.1f}%)")
        print(f"  下跌:       {down}  ({down/total*100:.1f}%)")
        print(f"  平盘:       {flat}")
        print(f"  涨幅>5%:    {up_gt5}")
        print(f"  跌幅>5%:    {down_gt5}")
        print(f"  涨跌比:     {up}:{down} = {up/max(down,1):.2f}")
    except Exception as e:
        print(f"  获取失败: {e}")
    print()


def main():
    if len(sys.argv) < 2:
        print("用法: python market_overview.py [index|sector|concept|breadth|all]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    commands = {
        "index": show_index,
        "sector": show_sector,
        "concept": show_concept,
        "breadth": show_breadth,
    }

    if cmd == "all":
        for fn in commands.values():
            fn()
    elif cmd in commands:
        commands[cmd]()
    else:
        print(f"未知命令: {cmd}\n可用: index, sector, concept, breadth, all")
        sys.exit(1)


if __name__ == "__main__":
    main()
