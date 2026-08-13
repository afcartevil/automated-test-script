---
name: mtk-adapt-pillar3-router
description: MTK 适配柱 3 入口：消费 Pillar 3 Customization Inputs（口述优先），按 RULE/SM40 分流到 transsion-sunmao40-customization-features-adapt，输出 Pillar 3 Handoff。仅处理 requested_features 中明确「要做」的项。由 mtk-adapt-template-router 调度。
---

# 柱 3 — 客制化特性入口

## 用途

柱 3 **唯一入口**。处理 **RULE-1～4** 与 **SM40-01～33** 客制化特性适配。

**只**消费 `requested_features` 中用户 **明确要做** 的项；未声明项 **不改码**，收口时仅提示。

不负责：器件（柱 1）、基本充电能力参数（柱 2）、三柱顺序与输入包组装（总编排 router）。

## 何时进入

- **`mtk-adapt-template-router`** 调度且 `pillar3_customization: required`
- 用户口述或输入表已能还原 **至少一项「要做」** 的 RULE / SM40

**若口述与表均未给出任何「要做」项 → `status: blocked`，停止柱 3 改码，反问用户。**

## 输入与优先级

1. **默认**：本任务对话 **用户口述**（见 **`transsion-sunmao40-customization-features-adapt`** **RULE-0**）
2. **可选**：**`pillar3-customization-input.md`**（同 sunmao40 skill 目录）作自检
3. **冲突**：**口述优先**；冲突须反问确认

## 二级分流

| 用户意图 / 特性键 | 下游 |
|-------------------|------|
| 关机充电动画 / KPOC / `TRAN_CHARGER_KPOC_ANIMATION` / `CUSTOM_TRAN_LOGO` | **`transsion-sunmao40-customization-features-adapt`** → **RULE-2** 或 **SM40-16** |
| 开机工模 / 关机工模 | 同上 → **RULE-3** |
| `tc_charger.dtsi` 客制化块注释纪律 | 同上 → **RULE-4** |
| 其它客制化特性 | 同上 → **RULE-1**；或索引 skill **`mtk-adapt-template-feature-{placeholder,kpoc-charging,factory-mode}`** → Read sunmao40 对应 RULE |

**落盘正文一律 `Read` `transsion-sunmao40-customization-features-adapt`**；索引 skill 仅名称兼容。

## 最小输入契约

- **要做** 的 RULE / SM40 列表 + 关键参数（GPIO、宏、`键=值` 等）
- KPOC（RULE-2 / SM40-16）：`TRAN_CHARGER_KPOC_ANIMATION`、`CUSTOM_TRAN_LOGO`（品牌不确定时必填）
- 工模（RULE-3）：工模类型、进入/退出条件、是否影响充电链路
- 不做且无工作量时须说明 **「此项特性无适配工作量」**

## 输出契约

输出 **Pillar Handoff Output**（`pillar: 3`），须含：
- 已执行的 RULE / SM40 与落盘摘要
- **收口**：章节目录内 **未声明「要做」** 的 RULE/SM40（**仅提示，不实施**）
- 可选：输入表 **「是否需要支持」= 否** 的摘要

## 边界

- 本 router **不直接改文件**；实现规则在 sunmao40 正文。
- **禁止**对用户未声明「要做」的特性擅自改参。
- 排障 / 根因分析 → `analysis/` 排障 skill，不经本柱。
