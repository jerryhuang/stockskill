#!/usr/bin/env python3
"""
共用快速数据获取模块。
- curl_cffi 优先，回退 requests/urllib
- 内存缓存 + 文件缓存，避免短时间内重复请求
- 请求限速（令牌桶），防止被东方财富封 IP
- 失败自动重试（指数退避）
"""

import json
import time
import os
import hashlib
import threading
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# ═══════════════════════════════════════════════════════════
#  缓存配置（秒）- 交易时段建议 30-60s，非交易时段可更长
# ═══════════════════════════════════════════════════════════
CACHE_TTL = {
    "index": 30,        # 指数行情
    "all_spot": 60,     # 全市场行情（最重的请求）
    "fund_flow": 120,   # 个股资金流向
    "default": 60,
}

_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════
#  令牌桶限速器 - 控制整体请求频率
# ═══════════════════════════════════════════════════════════
class _RateLimiter:
    """令牌桶算法，限制每秒最大请求数"""
    def __init__(self, rate: float = 8.0, burst: int = 15):
        self.rate = rate        # 每秒补充令牌数
        self.burst = burst      # 桶容量上限
        self.tokens = burst
        self.last_time = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_time
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_time = now

            if self.tokens >= 1:
                self.tokens -= 1
                return
            wait = (1 - self.tokens) / self.rate
        time.sleep(wait)
        with self.lock:
            self.tokens = max(0, self.tokens - 1)

_limiter = _RateLimiter(rate=8.0, burst=15)

# ═══════════════════════════════════════════════════════════
#  内存缓存
# ═══════════════════════════════════════════════════════════
_mem_cache = {}
_mem_lock = threading.Lock()


def _cache_get(key: str, ttl: int):
    """先查内存缓存，再查文件缓存"""
    with _mem_lock:
        if key in _mem_cache:
            ts, data = _mem_cache[key]
            if time.time() - ts < ttl:
                return data

    cache_file = os.path.join(_CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".json")
    if os.path.exists(cache_file):
        try:
            mtime = os.path.getmtime(cache_file)
            if time.time() - mtime < ttl:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                with _mem_lock:
                    _mem_cache[key] = (time.time(), data)
                return data
        except Exception:
            pass
    return None


def _cache_set(key: str, data):
    """同时写入内存和文件缓存"""
    with _mem_lock:
        _mem_cache[key] = (time.time(), data)

    cache_file = os.path.join(_CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".json")
    try:
        with open(cache_file, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  HTTP 会话
# ═══════════════════════════════════════════════════════════
_session = None


def _ensure_session():
    global _session
    if _session is not None:
        return
    try:
        from curl_cffi.requests import Session
        _session = Session(impersonate="chrome")
    except ImportError:
        import requests as _req
        _session = _req.Session()
        _session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })


def _get(url: str, timeout: int = 30, retries: int = 3) -> dict:
    """带限速和重试的 HTTP GET"""
    _ensure_session()
    last_err = None
    for attempt in range(retries):
        _limiter.acquire()
        try:
            resp = _session.get(url, timeout=timeout)
            text = resp.text
            if text.startswith("jQuery") or text.startswith("callback"):
                text = text[text.index("(") + 1: text.rindex(")")]
            return json.loads(text)
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))  # 1.5s, 3s 退避
    # curl_cffi 偶发被对端直接断开时，回退到 requests 再试一次
    try:
        import requests as _req  # type: ignore

        r = _req.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://quote.eastmoney.com/",
            },
        )
        text = r.text
        if text.startswith("jQuery") or text.startswith("callback"):
            text = text[text.index("(") + 1: text.rindex(")")]
        return json.loads(text)
    except Exception:
        raise last_err


# ═══════════════════════════════════════════════════════════
#  公开接口
# ═══════════════════════════════════════════════════════════

def _fetch_page(pn: int, fields: str, fs: str) -> list:
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fields={fields}&fs={fs}&_type=json"
    )
    try:
        data = _get(url)
        return data.get("data", {}).get("diff", [])
    except Exception:
        return []


def get_all_a_stock_spot() -> pd.DataFrame:
    """
    获取全部A股实时行情（~5800只）。
    带缓存：60秒内重复调用直接返回缓存数据。
    并行度降至 6，配合令牌桶限速，避免触发反爬。
    """
    cache_key = "all_a_stock_spot"
    cached = _cache_get(cache_key, CACHE_TTL["all_spot"])
    if cached is not None:
        return _items_to_df(cached)

    fields = "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f22,f23"
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

    first_url = (
        f"https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
        f"&fields={fields}&fs={fs}&_type=json"
    )
    data = _get(first_url)
    total = data.get("data", {}).get("total", 0)
    first_page = data.get("data", {}).get("diff", [])

    if total == 0:
        return pd.DataFrame()

    total_pages = (total + 99) // 100
    all_items = list(first_page)

    if total_pages > 1:
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(_fetch_page, pn, fields, fs): pn
                for pn in range(2, total_pages + 1)
            }
            for future in as_completed(futures):
                items = future.result()
                all_items.extend(items)

    _cache_set(cache_key, all_items)
    return _items_to_df(all_items)


def _items_to_df(items: list) -> pd.DataFrame:
    rows = []
    for item in items:
        rows.append({
            "代码": item.get("f12", ""),
            "名称": item.get("f14", ""),
            "最新价": item.get("f2"),
            "涨跌幅": item.get("f3"),
            "涨跌额": item.get("f4"),
            "成交量": item.get("f5"),
            "成交额": item.get("f6"),
            "振幅": item.get("f7"),
            "换手率": item.get("f8"),
            "市盈率": item.get("f9"),
            "量比": item.get("f10"),
            "最高": item.get("f15"),
            "最低": item.get("f16"),
            "今开": item.get("f17"),
            "昨收": item.get("f18"),
            "总市值": item.get("f20"),
            "流通市值": item.get("f21"),
            "涨速": item.get("f22"),
            "市净率": item.get("f23"),
        })
    df = pd.DataFrame(rows)
    num_cols = ["最新价", "涨跌幅", "涨跌额", "成交量", "成交额", "振幅", "换手率",
                "市盈率", "量比", "最高", "最低", "今开", "昨收", "总市值", "流通市值", "涨速", "市净率"]
    for col in num_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_index_quotes() -> pd.DataFrame:
    """获取主要指数行情（单次请求，带缓存）。"""
    cache_key = "index_quotes"
    cached = _cache_get(cache_key, CACHE_TTL["index"])
    if cached is not None:
        df = pd.DataFrame(cached)
        for col in ["最新价", "涨跌幅", "涨跌额", "成交额"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    secids = ",".join([
        "1.000001", "0.399001", "0.399006", "1.000688",
        "1.000300", "1.000905", "1.000852", "0.399303",
    ])
    url = (
        f"https://push2.eastmoney.com/api/qt/ulist.np/get?"
        f"fields=f2,f3,f4,f6,f12,f14&secids={secids}&_type=json"
    )
    data = _get(url)
    items = data.get("data", {}).get("diff", [])
    rows = []
    for item in items:
        price = item.get("f2", 0)
        pct = item.get("f3", 0)
        change = item.get("f4", 0)
        amount = item.get("f6", 0)
        rows.append({
            "指数": item.get("f14", ""),
            "最新价": price / 100 if isinstance(price, (int, float)) and price > 1000 else price,
            "涨跌幅": pct / 100 if isinstance(pct, (int, float)) and abs(pct) < 10000 else pct,
            "涨跌额": change / 100 if isinstance(change, (int, float)) else change,
            "成交额": amount,
        })

    _cache_set(cache_key, rows)

    df = pd.DataFrame(rows)
    for col in ["最新价", "涨跌幅", "涨跌额", "成交额"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_stock_individual_fund_flow(code: str) -> pd.DataFrame:
    """获取个股资金流向（最近30日，带缓存）"""
    cache_key = f"fund_flow_{code}"
    cached = _cache_get(cache_key, CACHE_TTL["fund_flow"])
    if cached is not None:
        return pd.DataFrame(cached)

    market = "1" if code.startswith("6") else "0"
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?"
        f"secid={market}.{code}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57"
        f"&lmt=30&_type=json"
    )
    data = _get(url)
    klines = data.get("data", {}).get("klines", [])
    if not klines:
        return pd.DataFrame()

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 7:
            rows.append({
                "日期": parts[0],
                "主力净流入": float(parts[1]),
                "小单净流入": float(parts[2]),
                "中单净流入": float(parts[3]),
                "大单净流入": float(parts[4]),
                "超大单净流入": float(parts[5]),
            })

    _cache_set(cache_key, rows)
    return pd.DataFrame(rows)


def get_board_rank(board_type: str = "industry", top: int = 30) -> pd.DataFrame:
    """
    获取行业/概念板块涨跌幅排名（直连东方财富，带缓存）。

    - board_type: "industry" | "concept"
    - top: 返回前 N 行
    """
    board_type = (board_type or "").lower().strip()
    if board_type not in {"industry", "concept"}:
        raise ValueError("board_type must be 'industry' or 'concept'")

    cache_key = f"board_rank_{board_type}_{top}"
    cached = _cache_get(cache_key, CACHE_TTL.get("default", 60))
    if cached is not None:
        return pd.DataFrame(cached)

    # 行业板块: m:90+t:2  概念板块: m:90+t:3
    fs = "m:90+t:2" if board_type == "industry" else "m:90+t:3"
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
        "&fltt=2&invt=2&fid=f3"
        f"&fs={fs}"
        "&fields=f12,f14,f2,f3,f62,f69,f75"
        "&_type=json"
    )
    data = _get(url)
    diff = data.get("data", {}).get("diff", []) or []

    rows = []
    for it in diff[: max(1, min(int(top), 100))]:
        rows.append(
            {
                "代码": it.get("f12", ""),
                "名称": it.get("f14", ""),
                "最新价": it.get("f2"),
                "涨跌幅": it.get("f3"),
                "主力净额": it.get("f62"),
                "领涨股": it.get("f69") or it.get("f75") or "",
            }
        )

    _cache_set(cache_key, rows)
    df = pd.DataFrame(rows)
    for col in ["最新价", "涨跌幅", "主力净额"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def clear_cache():
    """手动清除所有缓存"""
    global _mem_cache
    with _mem_lock:
        _mem_cache = {}
    for f in os.listdir(_CACHE_DIR):
        try:
            os.remove(os.path.join(_CACHE_DIR, f))
        except Exception:
            pass
    print("缓存已清除")


if __name__ == "__main__":
    print("测试1: 获取主要指数...")
    t0 = time.time()
    idx = get_index_quotes()
    print(f"  耗时: {time.time()-t0:.1f}s, 获取 {len(idx)} 条")
    if not idx.empty:
        print(idx.to_string(index=False))

    print("\n测试2: 获取全市场行情...")
    t0 = time.time()
    df = get_all_a_stock_spot()
    print(f"  耗时: {time.time()-t0:.1f}s, 获取 {len(df)} 只")

    print("\n测试3: 命中缓存（应瞬间返回）...")
    t0 = time.time()
    df2 = get_all_a_stock_spot()
    print(f"  耗时: {time.time()-t0:.3f}s, 获取 {len(df2)} 只 ← 缓存命中")
