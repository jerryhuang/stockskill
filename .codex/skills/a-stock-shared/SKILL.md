---
name: a-stock-shared
description: A股数据获取共享模块，提供快速并行的东方财富API访问、缓存、限速。被其他a-stock-*系列skill的脚本依赖。当其他A股skill需要fast_api模块时自动使用。
---

# A股共享数据模块

本模块为其他 `a-stock-*` 系列 skill 提供共享的数据获取能力。

## 依赖

```bash
pip install akshare pandas tabulate
```

## 提供的API

`scripts/fast_api.py` 导出以下函数：

- `get_index_quotes()` → 主要指数行情（单次请求，~7秒）
- `get_all_a_stock_spot()` → 全市场行情（~5800只，并行分页，~15-30秒）
- `get_stock_individual_fund_flow(code)` → 个股资金流向30日

## 特性

- 令牌桶限速（8 req/s），防止被封IP
- 内存+文件双层缓存（指数30s，全市场60s，资金流120s）
- 失败自动重试（指数退避）
- curl_cffi 优先，回退 requests

## 其他 skill 引用方式

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../a-stock-shared/scripts"))
from fast_api import get_index_quotes, get_all_a_stock_spot
```
