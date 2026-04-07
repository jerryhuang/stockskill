#!/usr/bin/env python3
"""
后台自动盯盘：同进程调用 hub 函数，共享内存缓存，避免重复API请求。
只需启动一次，后续每隔N分钟自动扫描直到收盘。

用法：
  python auto_monitor.py              # 默认间隔45分钟
  python auto_monitor.py --interval 30
  python auto_monitor.py --once        # 只跑一轮
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "../../../.."))
_STATE_DIR = os.path.join(_REPO_ROOT, ".codex", "state")
os.makedirs(_STATE_DIR, exist_ok=True)

sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "../../a-stock-shared/scripts")))
sys.path.insert(0, _HERE)

MONITOR_FILE = os.path.join(_STATE_DIR, "monitor_latest.json")
MONITOR_LOG = os.path.join(_STATE_DIR, "monitor_log.txt")

TRADING_HOURS = [
    (9, 25, 11, 35),
    (12, 55, 15, 5),
]


def _in_trading_hours() -> bool:
    now = datetime.now()
    t = now.hour * 60 + now.minute
    for sh, sm, eh, em in TRADING_HOURS:
        if sh * 60 + sm <= t <= eh * 60 + em:
            return True
    return False


def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(MONITOR_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _safe_json(obj):
    """确保 JSON 可序列化"""
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json(v) for v in obj]
    return obj


def run_one_round() -> dict:
    _log("开始本轮扫描（同进程，共享缓存）...")

    import hub

    hub.ensure_state_files()
    cfg = hub._load_json(hub._config_path(), hub._default_config())

    # 1) 拉全市场快照（后续所有计算共享这份数据）
    df_spot = None
    stats = {}
    try:
        df_spot = hub._get_all_spot_df()
        if df_spot is not None and not df_spot.empty:
            stats = hub._breadth_stats_from_spot(df_spot)
    except Exception as e:
        _log(f"全市场快照失败: {e}")

    # 2) 指数
    idx_list = []
    try:
        idx_df = hub._index_quotes_df()
        if idx_df is not None and not idx_df.empty:
            for name in ["上证指数", "深证成指", "创业板指", "科创50", "沪深300", "中证1000", "国证2000"]:
                sub = idx_df[idx_df["指数"] == name]
                if not sub.empty:
                    r = sub.iloc[0]
                    idx_list.append({"name": name, "close": round(float(r["最新价"]), 2), "change_pct": round(float(r["涨跌幅"]), 2)})
    except Exception as e:
        _log(f"指数拉取失败: {e}")

    # 3) 题材
    themes = []
    try:
        zt_df = hub._fetch_zt_pool_df()
        themes = hub._themes_from_zt_pool(zt_df, top_n=int(cfg["report"]["top_theme_n"]))
    except Exception as e:
        _log(f"题材拉取失败: {e}")

    # 4) 环境判断
    stance, stance_note = ("unknown", "数据不足")
    if stats:
        stance, stance_note = hub._stance_from_stats(stats, cfg)

    # 5) 筛选（复用上面的 df_spot，零额外请求）
    candidates = []
    try:
        candidates = hub._screen_candidates(df_spot, themes, cfg)
    except Exception as e:
        _log(f"筛选失败: {e}")

    # 6) 入场判断
    disc = cfg.get("discipline", {})
    entry_allowed = stats.get("ratio", 0) >= disc.get("entry_min_breadth_ratio", 0.4) if stats else False

    # 7) 持仓检查
    open_trades = [t for t in hub._load_trades() if t.get("status") == "open"]

    snapshot = _safe_json({
        "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "indices": idx_list,
        "breadth": stats,
        "stance": stance,
        "stance_note": stance_note,
        "entry_allowed": entry_allowed,
        "themes": themes[:5],
        "screen_top": candidates[:5],
        "screen_all": candidates,
        "open_trades": open_trades,
        "discipline": disc,
    })

    try:
        tmp = MONITOR_FILE + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        os.replace(tmp, MONITOR_FILE)
        _log(f"结果已写入 {MONITOR_FILE}")
    except Exception as e:
        _log(f"写入失败: {e}")

    ratio_str = f"{stats['ratio']:.2f}" if stats and "ratio" in stats else "?"
    _log(f"本轮完成 | 环境={stance} | 涨跌比={ratio_str} | 可入场={entry_allowed} | 候选={len(candidates)}只")

    return snapshot


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=45, help="扫描间隔（分钟）")
    parser.add_argument("--once", action="store_true", help="只跑一轮")
    args = parser.parse_args()

    _log(f"=== 自动盯盘启动 | 间隔 {args.interval} 分钟 | 同进程模式 ===")

    if args.once:
        run_one_round()
        return

    while True:
        if _in_trading_hours():
            try:
                run_one_round()
            except Exception as e:
                _log(f"本轮异常: {e}")
        else:
            _log("非交易时段，跳过。")

        _log(f"下次扫描: {args.interval} 分钟后")
        time.sleep(args.interval * 60)

        now = datetime.now()
        if now.hour >= 15 and now.minute >= 10:
            _log("收盘后停止。")
            break


if __name__ == "__main__":
    main()
