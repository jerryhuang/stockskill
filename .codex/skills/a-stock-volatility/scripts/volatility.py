#!/usr/bin/env python3
"""A股市场波动与情绪分析 - 使用共享快速API"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../a-stock-shared/scripts"))
from fast_api import get_all_a_stock_spot

import akshare as ak
import pandas as pd
import numpy as np
from tabulate import tabulate

pd.set_option("display.unicode.ambiguous_as_wide", True)
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 20)


def get_limit_stats():
    """涨跌停统计"""
    print("=" * 60)
    print("📊 今日涨跌停统计")
    print("=" * 60)

    try:
        df = get_all_a_stock_spot()
        if df.empty:
            print("  未获取到数据")
            return

        valid = df[pd.notna(df["涨跌幅"])].copy()
        non_st = valid[~valid["名称"].str.contains("ST|退市", na=False)]

        total = len(non_st)
        pct = non_st["涨跌幅"].astype(float)

        limit_up = len(pct[pct >= 9.9])
        limit_up_20 = len(pct[pct >= 19.9])
        limit_down = len(pct[pct <= -9.9])
        limit_down_20 = len(pct[pct <= -19.9])
        up = len(pct[pct > 0])
        down = len(pct[pct < 0])
        flat = len(pct[pct == 0])
        up_gt5 = len(pct[pct >= 5])
        up_gt7 = len(pct[pct >= 7])
        down_gt5 = len(pct[pct <= -5])

        print(f"""
  总股票数(剔除ST):  {total}
  ─────────────────────────────
  涨停(10%):        {limit_up}
  涨停(20%/创业板): {limit_up_20}
  跌停(10%):        {limit_down}
  跌停(20%):        {limit_down_20}
  ─────────────────────────────
  上涨:             {up}  ({up/total*100:.1f}%)
  下跌:             {down}  ({down/total*100:.1f}%)
  平盘:             {flat}
  涨幅>5%:          {up_gt5}
  涨幅>7%:          {up_gt7}
  跌幅>5%:          {down_gt5}
  ─────────────────────────────
  涨跌比:           {up}:{down} = {up/max(down,1):.2f}
""")
    except Exception as e:
        print(f"  获取数据失败: {e}")


def get_limit_up_detail():
    """涨停股明细"""
    print("=" * 70)
    print("🔴 今日涨停股明细")
    print("=" * 70)

    try:
        df = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if df is not None and not df.empty:
            rows = []
            for i, row in df.iterrows():
                r = {"序号": i + 1}
                for col in df.columns:
                    if "代码" in col: r["代码"] = row[col]
                    elif "名称" in col: r["名称"] = str(row[col])[:8]
                    elif "涨跌幅" in col: r["涨跌幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                    elif "连板数" in col or "连板" in col: r["连板"] = int(row[col]) if pd.notna(row[col]) else ""
                    elif "首次封板时间" in col or "封板时间" in col: r["封板时间"] = str(row[col])
                    elif "所属行业" in col or "行业" in col: r["行业"] = str(row[col])[:8] if pd.notna(row[col]) else ""
                    elif "炸板次数" in col: r["炸板"] = int(row[col]) if pd.notna(row[col]) else 0
                rows.append(r)
            print(f"  涨停家数: {len(df)}\n")
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  今日无涨停数据（可能非交易时段）")
    except Exception as e:
        print(f"  获取涨停数据失败: {e}")
    print()


def get_limit_down_detail():
    """跌停股明细"""
    print("=" * 70)
    print("🟢 今日跌停股明细")
    print("=" * 70)

    try:
        df = ak.stock_zt_pool_dtgc_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if df is not None and not df.empty:
            rows = []
            for i, row in df.iterrows():
                r = {"序号": i + 1}
                for col in df.columns:
                    if "代码" in col: r["代码"] = row[col]
                    elif "名称" in col: r["名称"] = str(row[col])[:8]
                    elif "涨跌幅" in col: r["涨跌幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                rows.append(r)
            print(f"  跌停家数: {len(df)}\n")
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  今日无跌停数据")
    except Exception as e:
        print(f"  获取跌停数据失败: {e}")
    print()


def get_streak_board():
    """连板股梳理"""
    print("=" * 70)
    print("🔥 连板股梳理（按连板高度排序）")
    print("=" * 70)

    try:
        df = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if df is not None and not df.empty:
            streak_col = next((c for c in df.columns if "连板" in c), None)
            if streak_col:
                df_sorted = df.sort_values(by=streak_col, ascending=False)
                multi = df_sorted[df_sorted[streak_col] >= 2]
                if not multi.empty:
                    rows = []
                    for _, row in multi.iterrows():
                        r = {}
                        for col in df.columns:
                            if "代码" in col: r["代码"] = row[col]
                            elif "名称" in col: r["名称"] = str(row[col])[:8]
                            elif "连板" in col:
                                boards = int(row[col]) if pd.notna(row[col]) else 0
                                r["连板"] = boards
                                r["高度"] = "🔥" * min(boards, 10)
                            elif "涨跌幅" in col: r["涨跌幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                            elif "所属行业" in col or "行业" in col: r["行业"] = str(row[col])[:8] if pd.notna(row[col]) else ""
                        rows.append(r)
                    max_s = max(int(r.get("连板", 0)) for r in rows)
                    print(f"  最高连板: {max_s}板  |  2板以上: {len(rows)}只\n")
                    print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
                else:
                    print("  今日无连板股")
        else:
            print("  今日无涨停数据")
    except Exception as e:
        print(f"  获取连板数据失败: {e}")
    print()


def get_limit_premium():
    """昨日涨停今日表现"""
    print("=" * 70)
    print("📈 昨日涨停今日表现（涨停溢价率）")
    print("=" * 70)

    try:
        df = ak.stock_zt_pool_previous_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if df is not None and not df.empty:
            rows = []
            pct_vals = []
            for i, row in df.head(30).iterrows():
                r = {"序号": i + 1}
                for col in df.columns:
                    if "代码" in col: r["代码"] = row[col]
                    elif "名称" in col: r["名称"] = str(row[col])[:8]
                    elif "涨跌幅" in col:
                        val = row[col]
                        r["今日涨跌幅%"] = f"{val:.2f}" if pd.notna(val) else ""
                        if pd.notna(val): pct_vals.append(float(val))
                rows.append(r)

            if pct_vals:
                avg = np.mean(pct_vals)
                median = np.median(pct_vals)
                pos = sum(1 for v in pct_vals if v > 0)
                print(f"  昨日涨停: {len(df)}只  今日上涨: {pos}只  今日下跌: {len(pct_vals)-pos}只")
                print(f"  平均溢价率: {avg:.2f}%  中位数: {median:.2f}%\n")
            print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  未获取到数据")
    except Exception as e:
        print(f"  获取数据失败: {e}")
    print()


def get_sentiment():
    """市场情绪综合分析"""
    print("=" * 70)
    print("🌡️  市场情绪综合分析")
    print("=" * 70)

    score = 0
    details = []

    try:
        df = get_all_a_stock_spot()
        if not df.empty:
            valid = df[pd.notna(df["涨跌幅"])].copy()
            non_st = valid[~valid["名称"].str.contains("ST|退市", na=False)]
            pct = non_st["涨跌幅"].astype(float)
            total = len(pct)
            up = len(pct[pct > 0])
            down = len(pct[pct < 0])
            limit_up = len(pct[pct >= 9.9])
            limit_down = len(pct[pct <= -9.9])
            ratio = up / max(down, 1)

            s = 20 if ratio > 3 else (15 if ratio > 2 else (10 if ratio > 1 else (5 if ratio > 0.5 else 0)))
            score += s
            details.append(f"  涨跌比: {up}:{down} = {ratio:.2f}  → {s}/20")

            s = 20 if limit_up > 120 else (15 if limit_up > 80 else (10 if limit_up > 50 else (5 if limit_up > 30 else 0)))
            score += s
            details.append(f"  涨停数: {limit_up}  → {s}/20")

            s = 20 if limit_down < 2 else (15 if limit_down < 5 else (10 if limit_down < 15 else (5 if limit_down < 30 else 0)))
            score += s
            details.append(f"  跌停数: {limit_down}  → {s}/20")

            mean_pct = pct.mean()
            s = 20 if mean_pct > 2 else (15 if mean_pct > 1 else (10 if mean_pct > 0 else (5 if mean_pct > -1 else 0)))
            score += s
            details.append(f"  市场均涨幅: {mean_pct:.2f}%  → {s}/20")
    except Exception as e:
        details.append(f"  获取行情数据失败: {e}")

    try:
        zt_df = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if zt_df is not None and not zt_df.empty:
            streak_col = next((c for c in zt_df.columns if "连板" in c), None)
            if streak_col:
                max_streak = zt_df[streak_col].max()
                s = 20 if max_streak >= 8 else (15 if max_streak >= 6 else (10 if max_streak >= 4 else (5 if max_streak >= 3 else 0)))
                score += s
                details.append(f"  连板高度: {int(max_streak)}板  → {s}/20")
    except Exception:
        details.append("  连板高度: 无数据")

    print("\n  【各维度评分】")
    for d in details:
        print(d)

    print(f"\n  ═══════════════════════════")
    print(f"  总分: {score}/100")

    if score >= 80:
        level, advice = "🔴 极度亢奋", "市场过热，注意高位风险，不宜追高"
    elif score >= 60:
        level, advice = "🟠 活跃", "赚钱效应好，可积极参与，控制仓位"
    elif score >= 40:
        level, advice = "🟡 中性", "市场一般，精选个股，适度参与"
    elif score >= 20:
        level, advice = "🟢 低迷", "市场弱势，轻仓或观望"
    else:
        level, advice = "🔵 冰点", "极度恐慌，关注反转信号"

    print(f"  情绪级别: {level}")
    print(f"  操作建议: {advice}")
    print(f"  ═══════════════════════════\n")


def get_unusual_stocks():
    """市场异动股"""
    print("=" * 70)
    print("⚡ 市场异动股")
    print("=" * 70)

    for label, symbol in [("大笔买入", "大笔买入"), ("急速涨停", "急速涨停"), ("大笔卖出", "大笔卖出")]:
        try:
            df = ak.stock_changes_em(symbol=symbol)
            if df is not None and not df.empty:
                print(f"\n  【{label}】")
                rows = []
                for i, row in df.head(15 if "买" in label or "卖" in label else 10).iterrows():
                    r = {"序号": i + 1}
                    for col in df.columns:
                        if "代码" in col: r["代码"] = row[col]
                        elif "名称" in col: r["名称"] = str(row[col])[:8]
                        elif "涨跌幅" in col: r["涨跌幅%"] = f"{row[col]:.2f}" if pd.notna(row[col]) else ""
                    rows.append(r)
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        except Exception:
            pass
    print()


def get_theme_strength(top: int = 15):
    """题材强度（基于涨停池聚合：数量 + 连板加权）"""
    print("=" * 70)
    print("🧭 题材强度 Top（基于涨停池/连板加权）")
    print("=" * 70)

    try:
        zt_df = ak.stock_zt_pool_em(date=pd.Timestamp.now().strftime("%Y%m%d"))
        if zt_df is None or zt_df.empty:
            print("  未获取到涨停池数据")
            print()
            return

        cols = list(zt_df.columns)
        streak_col = next((c for c in cols if "连板" in c), None)
        industry_col = next((c for c in cols if "行业" in c), None)
        concept_col = next((c for c in cols if "概念" in c or "题材" in c), None)

        # 优先概念，其次行业（不同数据源字段会有差异）
        theme_col = concept_col or industry_col
        if not theme_col:
            print("  题材字段缺失（无概念/行业列）")
            print()
            return

        def to_int(x, default=1):
            try:
                v = int(x)
                return v if v > 0 else 1
            except Exception:
                return default

        import re

        def split_themes(raw: str):
            text = str(raw or "").strip()
            if not text or text == "nan":
                return []
            return [p.strip() for p in re.split(r"[;,，、/|]+", text) if p.strip()]

        agg = {}
        for _, row in zt_df.iterrows():
            themes = split_themes(row.get(theme_col, ""))
            if not themes:
                continue
            boards = to_int(row.get(streak_col, 1)) if streak_col else 1
            for theme in themes:
                a = agg.setdefault(theme, {"题材": theme, "涨停数": 0, "连板贡献": 0, "最高板": 1, "2板+": 0})
                a["涨停数"] += 1
                a["连板贡献"] += max(0, boards - 1)
                a["最高板"] = max(a["最高板"], boards)
                if boards >= 2:
                    a["2板+"] += 1

        rows = []
        for v in agg.values():
            # score: 单日涨停数 + 连板贡献 + 2板以上持续性
            score = v["涨停数"] + 0.4 * v["连板贡献"] + 0.8 * v["2板+"]
            rows.append(
                {
                    "题材": v["题材"],
                    "score": round(score, 2),
                    "涨停": v["涨停数"],
                    "2板+": v["2板+"],
                    "最高板": v["最高板"],
                }
            )

        rows.sort(key=lambda x: (x["score"], x["2板+"], x["最高板"], x["涨停"]), reverse=True)
        print(tabulate(rows[: max(1, int(top))], headers="keys", tablefmt="simple", stralign="right"))
    except Exception as e:
        print(f"  获取题材强度失败: {e}")
    print()


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python volatility.py limit-stats  # 涨跌停统计")
        print("  python volatility.py limit-up     # 涨停股明细")
        print("  python volatility.py limit-down   # 跌停股明细")
        print("  python volatility.py streak       # 连板股梳理")
        print("  python volatility.py premium      # 涨停溢价率")
        print("  python volatility.py sentiment    # 情绪综合分析")
        print("  python volatility.py theme        # 题材强度(涨停池聚合)")
        print("  python volatility.py unusual      # 市场异动")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    commands = {
        "limit-stats": get_limit_stats,
        "limit-up": get_limit_up_detail,
        "limit-down": get_limit_down_detail,
        "streak": get_streak_board,
        "premium": get_limit_premium,
        "sentiment": get_sentiment,
        "theme": get_theme_strength,
        "unusual": get_unusual_stocks,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"未知命令: {cmd}"); sys.exit(1)


if __name__ == "__main__":
    main()
