#!/usr/bin/env python3
"""A股市场全面分析 - 依次执行各模块"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".cursor/skills/shared"))
from fast_api import get_index_quotes, get_all_a_stock_spot, get_stock_individual_fund_flow

import akshare as ak
import pandas as pd
import numpy as np
from tabulate import tabulate

pd.set_option("display.unicode.ambiguous_as_wide", True)
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def run():
    # ── 1. 主要指数 ──
    section("📊 一、主要指数行情")
    try:
        idx = get_index_quotes()
        if not idx.empty:
            rows = []
            for _, r in idx.iterrows():
                rows.append({
                    "指数": r["指数"],
                    "最新价": f"{r['最新价']:.2f}",
                    "涨跌幅%": f"{r['涨跌幅']:.2f}",
                    "涨跌额": f"{r['涨跌额']:.2f}",
                    "成交额(亿)": f"{r['成交额']/1e8:.1f}" if pd.notna(r["成交额"]) else "",
                })
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        print(f"  获取失败: {e}")

    # ── 2. 涨跌统计 ──
    section("📊 二、全市场涨跌统计")
    df_all = None
    try:
        df_all = get_all_a_stock_spot()
        if not df_all.empty:
            valid = df_all[pd.notna(df_all["涨跌幅"])].copy()
            non_st = valid[~valid["名称"].str.contains("ST|退市", na=False)]
            total = len(non_st)
            pct = non_st["涨跌幅"].astype(float)
            up = len(pct[pct > 0])
            down = len(pct[pct < 0])
            flat = len(pct[pct == 0])
            limit_up = len(pct[pct >= 9.9])
            limit_down = len(pct[pct <= -9.9])
            up5 = len(pct[pct >= 5])
            dn5 = len(pct[pct <= -5])
            mean_pct = pct.mean()

            print(f"  总股票数: {total}  (剔除ST)")
            print(f"  上涨: {up} ({up/total*100:.1f}%)  下跌: {down} ({down/total*100:.1f}%)  平盘: {flat}")
            print(f"  涨停: {limit_up}  跌停: {limit_down}")
            print(f"  涨>5%: {up5}  跌>5%: {dn5}")
            print(f"  涨跌比: {up}:{down} = {up/max(down,1):.2f}")
            print(f"  市场均涨幅: {mean_pct:.2f}%")
    except Exception as e:
        print(f"  获取失败: {e}")

    # ── 3. 板块排名 ──
    section("📈 三、行业板块涨跌 Top/Bottom 10")
    try:
        sdf = ak.stock_board_industry_name_em()
        if sdf is not None and not sdf.empty:
            nc = next((c for c in sdf.columns if "板块名称" in c or "名称" in c), None)
            pc = next((c for c in sdf.columns if "涨跌幅" in c), None)
            lc = next((c for c in sdf.columns if "领涨" in c), None)
            if nc and pc:
                print("\n  【涨幅前10】")
                rows = []
                for i, r in sdf.head(10).iterrows():
                    d = {"排名": i+1, "板块": r[nc], "涨跌幅%": f"{r[pc]:.2f}" if pd.notna(r[pc]) else ""}
                    if lc: d["领涨股"] = r.get(lc, "")
                    rows.append(d)
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))

                print("\n  【跌幅前10】")
                rows = []
                for i, r in sdf.tail(10).iloc[::-1].iterrows():
                    d = {"板块": r[nc], "涨跌幅%": f"{r[pc]:.2f}" if pd.notna(r[pc]) else ""}
                    rows.append(d)
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        print(f"  获取失败: {e}")

    # ── 4. 概念板块热度 ──
    section("🔥 四、概念板块热度 Top 10")
    try:
        cdf = ak.stock_board_concept_name_em()
        if cdf is not None and not cdf.empty:
            nc = next((c for c in cdf.columns if "板块名称" in c or "名称" in c), None)
            pc = next((c for c in cdf.columns if "涨跌幅" in c), None)
            if nc and pc:
                rows = []
                for i, r in cdf.head(10).iterrows():
                    rows.append({"排名": i+1, "概念": r[nc], "涨跌幅%": f"{r[pc]:.2f}" if pd.notna(r[pc]) else ""})
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        print(f"  获取失败: {e}")

    # ── 5. 北向资金 ──
    section("💰 五、北向资金")
    try:
        ndf = ak.stock_hsgt_fund_flow_summary_em()
        if ndf is not None and not ndf.empty:
            north = ndf[ndf["资金方向"] == "北向"]
            for _, r in north.iterrows():
                board = r.get("板块", "")
                net = r.get("成交净买额", 0)
                idx_name = r.get("相关指数", "")
                idx_pct = r.get("指数涨跌幅", 0)
                print(f"  {board}: 净买入 {net:.2f}亿 ({idx_name} {idx_pct:+.2f}%)")
    except Exception as e:
        print(f"  获取失败: {e}")

    try:
        sh = ak.stock_hsgt_hist_em(symbol="沪股通")
        sz = ak.stock_hsgt_hist_em(symbol="深股通")
        if sh is not None and sz is not None:
            dc = next((c for c in sh.columns if "日期" in c), None)
            fc = next((c for c in sh.columns if "净买额" in c or "净流入" in c), None)
            if dc and fc:
                rows = []
                sh5 = sh.tail(5).reset_index(drop=True)
                sz5 = sz.tail(5).reset_index(drop=True)
                for i in range(len(sh5)):
                    sv = sh5.iloc[i].get(fc, 0) or 0
                    dv = sz5.iloc[i].get(fc, 0) if i < len(sz5) else 0
                    dv = dv or 0
                    total_v = sv + dv
                    rows.append({
                        "日期": str(sh5.iloc[i][dc])[:10],
                        "沪股通": f"{sv:.2f}",
                        "深股通": f"{dv:.2f}",
                        "合计(亿)": f"{total_v:.2f}",
                    })
                print("\n  最近5个交易日:")
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception:
        pass

    # ── 6. 涨停/连板 ──
    section("🔴 六、涨停与连板")
    try:
        zt = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if zt is not None and not zt.empty:
            sc = next((c for c in zt.columns if "连板" in c), None)
            nc = next((c for c in zt.columns if "名称" in c), None)
            cc = next((c for c in zt.columns if "代码" in c), None)
            ic = next((c for c in zt.columns if "行业" in c), None)
            print(f"  今日涨停: {len(zt)} 只")

            if sc:
                max_s = zt[sc].max()
                print(f"  最高连板: {int(max_s)} 板")
                multi = zt[zt[sc] >= 2].sort_values(sc, ascending=False)
                if not multi.empty:
                    print(f"\n  连板股（2板以上，共{len(multi)}只）:")
                    rows = []
                    for _, r in multi.iterrows():
                        d = {}
                        if cc: d["代码"] = r[cc]
                        if nc: d["名称"] = str(r[nc])[:8]
                        d["连板"] = int(r[sc])
                        if ic and pd.notna(r.get(ic)): d["行业"] = str(r[ic])[:10]
                        rows.append(d)
                    print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        print(f"  获取失败: {e}")

    # ── 7. 情绪打分 ──
    section("🌡️  七、市场情绪综合打分")
    score = 0
    if df_all is not None and not df_all.empty:
        valid = df_all[pd.notna(df_all["涨跌幅"])].copy()
        non_st = valid[~valid["名称"].str.contains("ST|退市", na=False)]
        pct = non_st["涨跌幅"].astype(float)
        total = len(pct)
        up = len(pct[pct > 0])
        down = len(pct[pct < 0])
        limit_up = len(pct[pct >= 9.9])
        limit_down = len(pct[pct <= -9.9])
        ratio = up / max(down, 1)
        mean_pct = pct.mean()

        s = 20 if ratio > 3 else (15 if ratio > 2 else (10 if ratio > 1 else (5 if ratio > 0.5 else 0)))
        score += s; print(f"  涨跌比 {ratio:.2f} → {s}/20")

        s = 20 if limit_up > 120 else (15 if limit_up > 80 else (10 if limit_up > 50 else (5 if limit_up > 30 else 0)))
        score += s; print(f"  涨停数 {limit_up} → {s}/20")

        s = 20 if limit_down < 2 else (15 if limit_down < 5 else (10 if limit_down < 15 else (5 if limit_down < 30 else 0)))
        score += s; print(f"  跌停数 {limit_down} → {s}/20")

        s = 20 if mean_pct > 2 else (15 if mean_pct > 1 else (10 if mean_pct > 0 else (5 if mean_pct > -1 else 0)))
        score += s; print(f"  市场均涨幅 {mean_pct:.2f}% → {s}/20")

    try:
        zt = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if zt is not None and not zt.empty:
            sc2 = next((c for c in zt.columns if "连板" in c), None)
            if sc2:
                ms = zt[sc2].max()
                s = 20 if ms >= 8 else (15 if ms >= 6 else (10 if ms >= 4 else (5 if ms >= 3 else 0)))
                score += s; print(f"  连板高度 {int(ms)}板 → {s}/20")
    except Exception:
        pass

    print(f"\n  {'═'*30}")
    print(f"  总分: {score}/100")
    if score >= 80:    print("  🔴 极度亢奋 | 市场过热，注意高位风险")
    elif score >= 60:  print("  🟠 活跃     | 赚钱效应好，可积极参与")
    elif score >= 40:  print("  🟡 中性     | 结构性行情，精选个股")
    elif score >= 20:  print("  🟢 低迷     | 市场偏弱，轻仓观望")
    else:              print("  🔵 冰点     | 极度恐慌，关注反转信号")
    print(f"  {'═'*30}")


if __name__ == "__main__":
    run()
