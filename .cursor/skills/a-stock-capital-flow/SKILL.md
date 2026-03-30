---
name: a-stock-capital-flow
description: 获取A股资金流向数据，包括北向资金持股排行、行业板块增持排行、板块主力资金流、个股主力资金流入流出。当用户询问北向资金、主力资金、资金流向、外资动向时使用。
---

# A股资金流向

## 注意

2024年8月起，北向资金「成交净买额」不再实时披露。本模块已适配新规，改用持股排行和行业增持数据反映外资动向。

## 使用方式

### 北向资金今日概览

```bash
python .cursor/skills/a-stock-capital-flow/scripts/capital_flow.py north
```

输出：沪深股通/港股通交易摘要、关联指数表现。

### 北向持股排行（Top 15）

```bash
python .cursor/skills/a-stock-capital-flow/scripts/capital_flow.py north-hold all
```

参数：`all`（沪深合计）、`sh`（仅沪股通）、`sz`（仅深股通）。

### 北向行业板块增持排行

```bash
python .cursor/skills/a-stock-capital-flow/scripts/capital_flow.py north-board
```

输出：各行业北向资金持股市值、增持幅度、增持最大股。

### 行业板块主力资金流向

```bash
python .cursor/skills/a-stock-capital-flow/scripts/capital_flow.py sector-flow
```

### 个股主力资金排行

```bash
python .cursor/skills/a-stock-capital-flow/scripts/capital_flow.py top-flow
```

### 个股资金流向明细

```bash
python .cursor/skills/a-stock-capital-flow/scripts/capital_flow.py stock-flow 600519
```

输出：30日内主力/大单/超大单/中单/小单资金流向。

## 解读指南

- **板块资金集中流入**：主力形成共识，关注主线方向
- **个股主力大幅净流入+放量**：可能有机构建仓
- **个股主力持续流出**：资金出逃，注意规避
- **北向持股占比高+持续增持**：外资长期看好
