---
name: mtk-adapt-template-router
description: MTK 项目适配总编排入口：整理或消费 Adaptation Input Packet，按固定顺序 handoff 到 mtk-adapt-pillar1-router、mtk-adapt-pillar2-router、mtk-adapt-pillar3-router 执行三柱落盘。老→新升级先由 mtk-adapt-upgrade-branch-orchestrator 生成输入包，再回到本 skill 串行调度三柱 router。
---

# MTK 适配总编排

## 用途

本 skill 是 MTK 项目适配的**总编排入口**，**不**替代各柱 router 的二级分流，**不**替代领域模板正文。

负责：
- 把用户口述 / Inventory / 其它 skill 输出整理成 **Adaptation Input Packet**
- 按 **柱 1 → 柱 2 → 柱 3** 顺序调度三个柱级 router
- 汇总每柱 **Pillar Handoff Output**，决定下一柱是否继续

不负责：
- 柱内器件/参数/客制化的二级分流（由各柱 router 完成）
- 直接改文件或写实现细节

## 柱级 router（执行落盘前必读）

| 柱 | Router skill | 目录 |
|----|--------------|------|
| 1 器件 | **`mtk-adapt-pillar1-router`** | `adapt/pillar1-device/` |
| 2 基本充电能力参数 | **`mtk-adapt-pillar2-router`** | `adapt/pillar2-parameters/` |
| 3 客制化特性 | **`mtk-adapt-pillar3-router`** | `adapt/pillar3-customization/` |

调度规则：
1. 根据 `Pillar Selection` 跳过 `skip` 的柱。
2. 每柱执行前 **`Read` 对应柱 router 全文**，按其分流表进入下游 skill。
3. **柱 1 未完成**且用户未明确「仅做柱 2/3」时，**不得**进入柱 2 落盘。
4. 柱 2 消费柱 1 handoff 中的器件事实；柱 3 只消费 `requested_features`。

## 标准输入：Adaptation Input Packet

字段未知时写 `unknown`；必备路径按 `mtk-adapt-upgrade-branch-orchestrator` 路径纪律回退后仍未知时 **停止反问**，不用全树盲搜补。

```markdown
## Adaptation Input Packet

### Scope
- mode: greenfield | upgrade | partial
- project_full:
- platform:
- kernel_version:
- aosp_root:
- old_tran_root: <upgrade only>

### Pillar Selection
- pillar1_device: required | skip | unknown
- pillar2_parameters: required | skip | unknown
- pillar3_customization: required | skip | unknown

### Evidence
- project_config:
- kernel_dws:
- preloader_codegen_dws:
- lk2_project_mk:
- tc_charger_lk_dtsi:
- charge_overlay:

### Pillar 1 Device Inputs
- charger_ic:
- pd_ic:
- charge_pump:
- gauge:
- bus_irq_gpio_power:

### Pillar 2 Parameter Inputs
- tc_charger_lk_targets:
- tc_charger_dtsi_targets:
- legacy_nodes:
- required_bridge_skills:

### Pillar 3 Customization Inputs
- requested_features:
- explicitly_not_required:
- pending_questions:
```

输入来源：
- **用户口述** → 先整理输入包，回述缺口，再进柱级 router。
- **升级** → `mtk-adapt-upgrade-branch-orchestrator` / `mtk-adapt-upgrade-inventory-checklist` 只补全输入包；落盘仍经本 skill → 三柱 router。

## 标准输出：Pillar Handoff Output

每柱完成后输出（格式由各柱 router 与下游 skill 回填）：

```markdown
## Pillar Handoff Output

### Pillar
- pillar: 1 | 2 | 3
- status: ready | blocked | partial
- downstream_skill:

### Inputs Consumed
- evidence:
- user_confirmed_items:
- assumptions:

### Changes To Apply
- file:
- node_or_macro:
- action:
- source:
- review_tag:

### Required Follow-up
- next_pillar:
- blocking_questions:
- validation:
```

## 执行流程

```text
Adaptation Input Packet
  -> mtk-adapt-template-router（本 skill：核对契约与柱顺序）
  -> mtk-adapt-pillar1-router -> device-* -> Pillar 1 Handoff
  -> mtk-adapt-pillar2-router -> basic-charging / bridge-* -> Pillar 2 Handoff
  -> mtk-adapt-pillar3-router -> sunmao40 -> Pillar 3 Handoff
```

## 通用纪律（绿场与升级共用）

1. **路径**：改码 / 分析前 **`Read` `transsion-aosp-path-conventions`**；`project_full` / DWS / overlay 拼接见 **`mtk-adapt-upgrade-branch-orchestrator`** §1～§3。
2. **禁止**从 AOSP 根或 `kernel-*` 根盲 `grep` 反推 `project_full`。
3. **升级前置**：老树 → 新树须先完成编排器 + Inventory（柱 0～2 信源），再 handoff 回本 skill。
4. **排障 vs 适配**：根因分析类请求先回到 `analysis/` 下排障 skill，不经本编排链。

## 边界

- 本 skill **不直接改文件**。
- 柱内二级分流、强制 Read 表、最小输入契约 → **各柱 router** 正文。
- 历史文档中的「三柱总路由」指 **本 skill + 三柱 router** 组合；单柱任务可直接 **`Read` 对应柱 router**（须自备输入包中该柱 section）。

---

## 修订记录

| 日期 | 摘要 |
|------|------|
| 2026-06-30 | 拆分为总编排 + `mtk-adapt-pillar{1,2,3}-router` 三柱入口；柱内分流下沉。 |
