---
name: mtk-adapt-upgrade-platform-delta-table
description: 老分支→新分支平台级差分规则表（骨架）。版本对版本闸门、不可机械拷贝项按表预留，细则链接到现有模板与 bridge skill。
funcType: "AI自动化适配"
category: "驱动"
---

# MTK 升级适配：Platform Delta 表（骨架）

## 状态

本文为**骨架**：表格主体仅列列名与示例占位行，具体规则待按平台（Android 代际、KDM 6.1/6.6/6.12、Tran 栈版本）逐项与你对齐代码后填充。

## 用途

（预留：与 `mtk-adapt-template-basic-charging-capability`、各 `device-*` 模板的关系——本表不写长 dtsi 模板，只写「差分闸门」。）

---

## 修订记录

| 日期 | 摘要 |
|------|------|
| 2026-05-12 | 项目路径求解与「禁止全树 grep」见 `mtk-adapt-upgrade-branch-orchestrator` §路径解析纪律；本表规则行仍待按平台填充。 |
| 2026-05-12 | **表 3** 新增闸门行：**`mtk_pe50`→`tc_pe5`** 热限语义须 **`Read` `transsion-pe5-migrate-dual-cp-k612`**；索引编排器 **§13**。 |

## 表 1 — 内核大版本 / KDM 跃迁（行待填充）

| 旧侧（示例列） | 新侧（示例列） | 不可机械拷贝项摘要 | 权威引用 |
|----------------|----------------|--------------------|----------|
| （预留） | （预留） | （预留） | `mtk-adapt-template-basic-charging-capability` / 其它 |
| … | … | … | … |

---

## 表 2 — 框架选型与节点命名（extcon / battery_manager 等）

| 规则 ID | 条件（旧→新） | 应然行为 | 权威引用 |
|---------|----------------|----------|----------|
| （预留） | （预留） | （预留） | （预留） |

---

## 表 3 — 老 KDM 5.10 语义迁移闸门

| 闸门 | 说明 | 下一动作 |
|------|------|----------|
| 老树为 `kernel-5.10` / 老 `tran_chg` | （预留：判定条件写死或写 grep 判据） | **必须** 按 `transsion-charger-dtsi-driver-bridge` 四步执行后再做参数摘要 |
| **`&pe5` / `mtk_pe50.dtsi`→新 `tc_pe5`（6.12）** | 老 **`mtk_pe5.c`** 在 dual/third DVCHG 下对若干 **thermal `*_curlmt`** 使用 **`ita_lmt - (2*curlmt)`**；新 **`tc_pe5.c`** **无**该倍增，**恒减一次**。机械拷贝会导致热限与实机不符。 | **`Read` `transsion-pe5-migrate-dual-cp-k612`**；按项目判定是否对 SOURCE 热限表做 **×2 对齐**；见 **`mtk-adapt-upgrade-branch-orchestrator` §13**。 |
| 非 5.10 但跨大版本 | （预留） | （预留：可选 bridge） |

（预留：与 `transsion-charger-dtsi-driver-bridge` 中「典型 5.10→6.12」表的关系——本表不重复长对照，只保留索引行。）

---

## 表 4 — LK / Preloader 代际差异

| 规则 ID | 条件 | 应然行为 | 权威引用 |
|---------|------|----------|----------|
| （预留） | （预留） | （预留） | （预留） |

---

## 表 5 — DWS / GPIO 命名与双端（kernel vs preloader）

| 规则 ID | 条件 | 应然行为 | 权威引用 |
|---------|------|----------|----------|
| （预留） | （预留） | （预留） | `mtk-adapt-template-device-charge-pump` 等 |

---

## 表 6 — 与客户/法规相关的「禁止盲拷」

| 类别 | 说明 | 必填人类输入 |
|------|------|----------------|
| 电池包/温区 | （预留） | （预留） |
| 硬件改版 | （预留） | （预留） |
