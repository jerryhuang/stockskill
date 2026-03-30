---
name: a-stock-capital-flow
description: 获取A股资金流向数据，包括北向资金持股排行、行业板块增持排行、板块主力资金流、个股主力资金流入流出。当用户询问北向资金、主力资金、资金流向、外资动向时使用。注意：2024年8月起北向资金成交净买额不再披露，改用持股数据。
---

# A股资金流向

## 注意

2024年8月起，北向资金成交净买额不再实时披露。本模块已适配新规，改用持股排行和行业增持数据反映外资动向。

## 依赖

确保已安装: `pip install akshare pandas tabulate`

## 命令

### 北向资金今日概览
```bash
python .codex/skills/a-stock-capital-flow/scripts/capital_flow.py north
```

### 北向持股排行
```bash
python .codex/skills/a-stock-capital-flow/scripts/capital_flow.py north-hold all
```
参数: all（全部）、sh（沪股通）、sz（深股通）

### 北向行业板块增持排行
```bash
python .codex/skills/a-stock-capital-flow/scripts/capital_flow.py north-board
```

### 板块主力资金流向
```bash
python .codex/skills/a-stock-capital-flow/scripts/capital_flow.py sector-flow
```

### 个股主力资金排行
```bash
python .codex/skills/a-stock-capital-flow/scripts/capital_flow.py top-flow
```

### 个股资金明细
```bash
python .codex/skills/a-stock-capital-flow/scripts/capital_flow.py stock-flow 600519
```
