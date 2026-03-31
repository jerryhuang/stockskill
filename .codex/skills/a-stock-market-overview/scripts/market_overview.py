#!/usr/bin/env python3
"""A股大盘概览数据获取 - 使用共享快速API"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../a-stock-shared/scripts"))
from fast_api import get_index_quotes, get_all_a_stock_spot, get_board_rank

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

    try:
        df = get_board_rank("industry", top=31)
        if df is None or df.empty:
            raise RuntimeError("board_rank_empty")

        rows = []
        for i, row in df.iterrows():
            rows.append(
                {
                    "排名": i + 1,
                    "板块": row.get("名称", ""),
                    "涨跌幅%": f"{float(row.get('涨跌幅')):.2f}" if pd.notna(row.get("涨跌幅")) else "N/A",
                    "主力净额(亿)": f"{float(row.get('主力净额'))/1e8:.2f}" if pd.notna(row.get("主力净额")) else "N/A",
                    "领涨股": row.get("领涨股", ""),
                }
            )
        print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        # 降级到 akshare（可能仍会断连）
        try:
            import akshare as ak

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
        except Exception as e2:
            # 再降级：用涨停池按“行业”聚合，给短线主线参考
            try:
                import pandas as pd
                import akshare as ak

                zt = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
                if zt is None or zt.empty:
                    raise RuntimeError("zt_pool_empty")
                industry_col = next((c for c in zt.columns if "行业" in c), None)
                streak_col = next((c for c in zt.columns if "连板" in c), None)
                if not industry_col:
                    raise RuntimeError("no_industry_col")

                agg = {}
                for _, row in zt.iterrows():
                    industry = str(row.get(industry_col, "")).strip()
                    if not industry or industry == "nan":
                        continue
                    boards = 1
                    if streak_col:
                        try:
                            boards = int(row.get(streak_col, 1)) or 1
                        except Exception:
                            boards = 1
                    a = agg.setdefault(industry, {"板块": industry, "涨停": 0, "最高板": 1})
                    a["涨停"] += 1
                    a["最高板"] = max(a["最高板"], boards)
                rows = sorted(agg.values(), key=lambda x: (x["涨停"], x["最高板"]), reverse=True)[:31]
                for i, r in enumerate(rows, start=1):
                    r["排名"] = i
                print("  (板块榜不可用，已降级为“涨停池-行业聚合”)")
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
            except Exception as e3:
                print(f"  获取板块失败: {e} | 降级接口也失败: {e2} | 题材降级也失败: {e3}")
    print()


def show_concept():
    """概念板块热度"""
    print("=" * 60)
    print("🔥 概念板块热度 Top 20")
    print("=" * 60)

    try:
        df = get_board_rank("concept", top=20)
        if df is None or df.empty:
            raise RuntimeError("board_rank_empty")
        rows = []
        for i, row in df.iterrows():
            rows.append(
                {
                    "排名": i + 1,
                    "概念": row.get("名称", ""),
                    "涨跌幅%": f"{float(row.get('涨跌幅')):.2f}" if pd.notna(row.get("涨跌幅")) else "N/A",
                    "主力净额(亿)": f"{float(row.get('主力净额'))/1e8:.2f}" if pd.notna(row.get("主力净额")) else "N/A",
                }
            )
        print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        try:
            import akshare as ak

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
        except Exception as e2:
            # 再降级：用涨停池按“概念/题材”聚合
            try:
                import pandas as pd
                import akshare as ak

                zt = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
                if zt is None or zt.empty:
                    raise RuntimeError("zt_pool_empty")
                streak_col = next((c for c in zt.columns if "连板" in c), None)
                concept_col = next((c for c in zt.columns if "概念" in c or "题材" in c), None)
                # 某些时段涨停池不提供概念列，则降级为行业聚合作为“主线”参考
                group_col = concept_col or next((c for c in zt.columns if "行业" in c), None)
                if not group_col:
                    raise RuntimeError("no_concept_or_industry_col")

                agg = {}
                for _, row in zt.iterrows():
                    concept = str(row.get(group_col, "")).strip()
                    if not concept or concept == "nan":
                        continue
                    boards = 1
                    if streak_col:
                        try:
                            boards = int(row.get(streak_col, 1)) or 1
                        except Exception:
                            boards = 1
                    key_name = "概念" if concept_col else "行业"
                    a = agg.setdefault(concept, {key_name: concept, "涨停": 0, "最高板": 1})
                    a["涨停"] += 1
                    a["最高板"] = max(a["最高板"], boards)
                rows = sorted(agg.values(), key=lambda x: (x["涨停"], x["最高板"]), reverse=True)[:20]
                for i, r in enumerate(rows, start=1):
                    r["排名"] = i
                if concept_col:
                    print("  (概念榜不可用，已降级为“涨停池-概念聚合”)")
                else:
                    print("  (概念榜不可用且无概念列，已降级为“涨停池-行业聚合”)")
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
            except Exception as e3:
                print(f"  获取概念失败: {e} | 降级接口也失败: {e2} | 题材降级也失败: {e3}")
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
