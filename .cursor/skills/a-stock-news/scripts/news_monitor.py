#!/usr/bin/env python3
"""A股消息监控"""

import sys
import warnings
warnings.filterwarnings("ignore")

import akshare as ak
import pandas as pd
from tabulate import tabulate
from datetime import datetime, timedelta

pd.set_option("display.unicode.ambiguous_as_wide", True)
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 80)


def get_flash_news(count: int = 30):
    """获取财经快讯"""
    print("=" * 70)
    print("📰 财经快讯（实时）")
    print("=" * 70)

    try:
        df = ak.stock_info_global_em()
        if df is not None and not df.empty:
            rows = []
            for _, row in df.head(count).iterrows():
                r = {}
                for col in df.columns:
                    if "时间" in col or "date" in col.lower():
                        r["时间"] = str(row[col])
                    elif "内容" in col or "title" in col.lower() or "标题" in col:
                        content = str(row[col])
                        if len(content) > 80:
                            content = content[:77] + "..."
                        r["内容"] = content
                rows.append(r)

            if rows:
                for r in rows:
                    time_str = r.get("时间", "")
                    content = r.get("内容", "")
                    print(f"  [{time_str}] {content}")
            else:
                print("  未获取到快讯")
        else:
            print("  未获取到快讯数据")
    except Exception as e:
        print(f"  获取快讯失败: {e}")
        try:
            df = ak.stock_info_global_futu()
            if df is not None and not df.empty:
                for _, row in df.head(count).iterrows():
                    for col in df.columns:
                        if "内容" in col or "title" in col.lower() or "标题" in col:
                            content = str(row[col])
                            if len(content) > 80:
                                content = content[:77] + "..."
                            print(f"  {content}")
                            break
        except Exception:
            print("  备用接口也失败")
    print()


def get_stock_announce(code: str, count: int = 10):
    """获取个股公告"""
    code = code.strip()
    for prefix in ["sh", "sz", "bj"]:
        if code.lower().startswith(prefix):
            code = code[2:]

    print("=" * 70)
    print(f"📋 个股公告 [{code}]")
    print("=" * 70)

    try:
        df = ak.stock_notice_report(symbol=code)
        if df is not None and not df.empty:
            rows = []
            for _, row in df.head(count).iterrows():
                r = {}
                for col in df.columns:
                    if "日期" in col or "date" in col.lower() or "时间" in col:
                        r["日期"] = str(row[col])[:10]
                    elif "标题" in col or "公告" in col or "title" in col.lower():
                        title = str(row[col])
                        if len(title) > 60:
                            title = title[:57] + "..."
                        r["公告标题"] = title
                rows.append(r)

            if rows:
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="left"))
            else:
                print("  未解析到公告内容")
        else:
            print("  未获取到公告数据")
    except Exception as e:
        print(f"  获取公告失败: {e}")
        print("  提示: 部分接口可能需要更新 akshare 版本")
    print()


def get_stock_news(code: str):
    """获取个股相关新闻"""
    code = code.strip()
    for prefix in ["sh", "sz", "bj"]:
        if code.lower().startswith(prefix):
            code = code[2:]

    print("=" * 70)
    print(f"📰 个股新闻 [{code}]")
    print("=" * 70)

    try:
        df = ak.stock_news_em(symbol=code)
        if df is not None and not df.empty:
            rows = []
            for _, row in df.head(20).iterrows():
                r = {}
                for col in df.columns:
                    if "发布时间" in col or "时间" in col or "date" in col.lower():
                        r["时间"] = str(row[col])
                    elif "新闻标题" in col or "标题" in col or "title" in col.lower():
                        title = str(row[col])
                        if len(title) > 60:
                            title = title[:57] + "..."
                        r["标题"] = title
                    elif "新闻来源" in col or "来源" in col:
                        r["来源"] = str(row[col])
                rows.append(r)

            if rows:
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="left"))
        else:
            print("  未获取到新闻")
    except Exception as e:
        print(f"  获取新闻失败: {e}")
    print()


def get_cctv_news(date_str: str = None):
    """获取新闻联播文字稿"""
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")

    print("=" * 70)
    print(f"📺 新闻联播摘要 [{date_str}]")
    print("=" * 70)

    try:
        df = ak.news_cctv(date=date_str)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                title = ""
                content = ""
                for col in df.columns:
                    if "标题" in col or "title" in col.lower():
                        title = str(row[col])
                    elif "内容" in col or "content" in col.lower():
                        content = str(row[col])
                        if len(content) > 200:
                            content = content[:197] + "..."

                if title:
                    print(f"\n  【{title}】")
                    if content:
                        print(f"  {content}")
        else:
            print("  未获取到数据（可能非交易日或数据未更新）")
    except Exception as e:
        print(f"  获取新闻联播失败: {e}")
    print()


def get_economic_calendar():
    """获取财经日历"""
    print("=" * 70)
    print("📅 全球财经日历")
    print("=" * 70)

    try:
        df = ak.news_economic_baidu(date="today")
        if df is not None and not df.empty:
            rows = []
            for _, row in df.head(30).iterrows():
                r = {}
                for col in df.columns:
                    if "时间" in col:
                        r["时间"] = str(row[col])
                    elif "国家" in col or "地区" in col:
                        r["国家"] = str(row[col])
                    elif "事件" in col or "指标" in col:
                        event = str(row[col])
                        if len(event) > 40:
                            event = event[:37] + "..."
                        r["事件"] = event
                    elif "重要性" in col or "星级" in col:
                        r["重要性"] = str(row[col])
                    elif "前值" in col:
                        r["前值"] = str(row[col]) if pd.notna(row[col]) else ""
                    elif "预期" in col:
                        r["预期"] = str(row[col]) if pd.notna(row[col]) else ""
                    elif "公布" in col:
                        r["公布"] = str(row[col]) if pd.notna(row[col]) else ""
                rows.append(r)

            if rows:
                print(tabulate(rows, headers="keys", tablefmt="simple", stralign="right"))
        else:
            print("  未获取到日历数据")
    except Exception as e:
        print(f"  获取财经日历失败: {e}")
        print("  提示: 可尝试 akshare 其他财经日历接口")
    print()


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python news_monitor.py flash [N]            # 财经快讯(最近N条)")
        print("  python news_monitor.py announce 600519 [N]  # 个股公告")
        print("  python news_monitor.py stock-news 600519    # 个股新闻")
        print("  python news_monitor.py cctv [YYYYMMDD]      # 新闻联播")
        print("  python news_monitor.py calendar             # 财经日历")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "flash":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        get_flash_news(count)

    elif cmd == "announce":
        if len(sys.argv) < 3:
            print("请提供股票代码")
            sys.exit(1)
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        get_stock_announce(sys.argv[2], count)

    elif cmd == "stock-news":
        if len(sys.argv) < 3:
            print("请提供股票代码")
            sys.exit(1)
        get_stock_news(sys.argv[2])

    elif cmd == "cctv":
        date_str = sys.argv[2] if len(sys.argv) > 2 else None
        get_cctv_news(date_str)

    elif cmd == "calendar":
        get_economic_calendar()

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
