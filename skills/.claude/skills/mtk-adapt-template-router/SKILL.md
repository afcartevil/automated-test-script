---
name: mtk-adapt-template-router
description: MTK 适配总路由：器件 / 基本充电能力参数 / 客制化特性三柱分流。柱 3 执行正文指向 transsion-sunmao40-customization-features-adapt；柱 3 **默认接受对话口述**（RULE-0），可选对照 **`pillar3-customization-input.md`**。新分支侧路径纪律、禁止全树反查、强制 Read 索引与升级 handoff 见正文「新分支侧通用纪律」。老→新升级时先经 mtk-adapt-upgrade-branch-orchestrator 柱0～2，再回到本 router 按相同三柱落盘。
funcType: "AI自动化适配"
category: "驱动"
---

# MTK 适配总路由

## 用途

这是 MTK 适配工作的顶层分流技能，不直接改配置文件。

## 新分支侧通用纪律（绿场与升级共用）

下列规则在新分支 AOSP 上执行适配时 **一律遵守**；正文细节与节点级对照以引用 skill 为准。

### 路径与搜索

1. **`project_full` / DWS / LK `tc_charger_lk.dtsi` / kernel charge overlay** 的拼接与验证顺序：`Read` **`mtk-adapt-upgrade-branch-orchestrator`** 中 **「路径解析纪律」§1～§3**（与 `mtk-adapt-template-device-pd-ic` / `mtk-adapt-template-device-charge-pump` §0.1～0.3 一致）。  
2. **禁止**从 AOSP 根或 `kernel-*` 根起对整树 **`grep` / 盲扫** 以反推 `project_full` 或板级路径；**仅允许**在 skill 已拼出的路径或其直接父目录内做有限搜索（同编排器路径纪律 **§2**）。  
3. 必备文件在规则内回退后仍缺失：**停止推断**，向用户列出已尝试路径并索要实际位置（同编排器 **§3**）。

### 三柱执行顺序与落地方式

1. **顺序固定**：**器件适配 → 基本充电能力参数适配 → 客制化特性适配**。不可跳过柱 1 直接堆柱 2 参数（除非用户明确范围仅限某一柱且已具备前置结论）。  
2. **落盘方式**：**柱 1** **`Read` 各 `mtk-adapt-template-device-*`**；**柱 2** **`Read` `mtk-adapt-template-basic-charging-capability`**；**柱 3（客制化特性）`Read` `transsion-sunmao40-customization-features-adapt`**（仅适配规则与 SM40 条目，**不含**本 router 的分流逻辑）。本 router **只负责分流与契约核对**，不替代各模板正文。  
3. **器件柱完成后（可选）**：对新旧 **`vendor/transsion/projects/<project_full>/ProjectConfig.mk`** 做 **diff**，查找未被本次模板覆盖的 **游离宏/行**（与 **`mtk-adapt-upgrade-inventory-checklist`** 块 D.2 一致）。

### 柱 3（客制化特性）输入与收口

- **输入**：**默认**为 **本任务对话中用户口述**（须能还原出：哪些 **RULE-*** / **SM40-*** **要做**、关键参数与 GPIO 等；见 **`transsion-sunmao40-customization-features-adapt`** **RULE-0**）。可选 **`d:\Users\guansen.wang\.cursor\skills\pillar3-customization-input.md`** 作自检表；**口述与表冲突时以对话为准**。若口述与表均未给出任何「要做」的柱 3 项：**停止柱 3 改码**，反问用户补全后再继续。
- **执行**：柱 3 落盘时 **`Read` `transsion-sunmao40-customization-features-adapt`**，**仅**处理用户 **明确要做** 的特性键；**未说要做** 的不改码。不做且无工作量时须在口述或表中说明 **「此项特性无适配工作量」**（见合并 skill **RULE-0**）。**禁止**对用户未声明「要做」的特性擅自改参。
- **收口**：答复中提示：章节目录内 **RULE / SM40** 中用户 **未声明「要做」** 的项（仅提示）；可选对照输入表 **「是否需要支持」= 否** 的摘要。**不**对未处理项做实现。

### 老分支 → 新分支时的前置（升级）

在已确认任务为 **老树 → 新树** 迁移时：  
1. 先完成 **`mtk-adapt-upgrade-branch-orchestrator`** + **`mtk-adapt-upgrade-inventory-checklist`** 所覆盖的 **柱 0～2 信源与语义准备**（含 DWS GPIO 溯源工作流），再按下面一级分流回到本 router **按柱执行**。  
2. **节点级迁移规则索引**（`tran_battery_aging` 跳过、`tran_otg`、`tran_auto_test`、`water_detect`、`pid_chg`、`support_alg`、`extcon_usb`、**`&pe5`/PE5 热限语义** 等）：以编排器 **路径解析纪律 §5～§13** 与 **`transsion-charger-dtsi-driver-bridge`** 为准，**不得**仅凭 compatible 字符串臆测等价。

### 强制 Read（闸门）

| 场景 | 必须先 Read 的 skill |
|------|------------------------|
| 老树含 **`tran_battery` / `tran,chg_fun`**，或同文件 **`jeita_*_chg_cur` / `pcb_*`** 需迁入新树 **`&charger`** | **`transsion-tran-battery-to-tc-charger-dtsi`** 全文 |
| 老树含 **`&pe5` / `mtk_pe50.dtsi` / `mediatek,charger,pe5`**，新树写 **`tc_pe5.dtsi`** 或核对 dual/third CP 热限 | **`transsion-pe5-migrate-dual-cp-k612`** |
| 广义的 DTSI↔驱动语义、OTG、上述 bridge 表覆盖的节点别名 | **`transsion-charger-dtsi-driver-bridge`**（按需）；**与上一行并存，不互相替代** |
| 平台级版本跃迁闸门（可选） | **`mtk-adapt-upgrade-platform-delta-table`** |

### 硬件静态描述 vs 策略参数

与 BOM/走线/器件手册强相关、且 **老新树可对读** 的字段（如 CP 从片 I2C 地址、与老树一致的 IRQ GPIO），若新侧疑似笔误，可按编排器路径纪律 **§4** 在新树对齐并 **落盘后告知用户**；**温区策略、PE5 数值语义、5.10→新栈迁移** 等须走 bridge / 专项 skill 与用户确认，**不适用**「静默直拷」。

---

## 升级自老分支（老内核 → 新内核链路）

当任务明确为 **老分支代码树 → 新分支代码树** 的充电/电源相关适配迁移（含 kernel 5.10 / 老 KDM 与 **kernel_device_modules-6.12** 等新 KDM 并存场景），**与绿场相同**，仍按本 skill **一级：器件 / 基本充电能力参数 / 客制化特性** 三柱分流；**升级专用前置**由编排器完成 **柱 0～2 的信源与语义准备**，再 **回到此处**按柱执行。

### 升级执行顺序（与 `mtk-adapt-upgrade-branch-orchestrator` 对齐）

1. **`mtk-adapt-upgrade-branch-orchestrator`** + **`mtk-adapt-upgrade-inventory-checklist`**：**柱 0**（用户 **`OLD_TRAN_ROOT`**、新侧路径拼凑、老文件列举、DWS 溯源）；**柱 2** 准备（bridge / `tran_battery` / PE5 migrate 等见编排器 **§5～§13** 与 **§3.2.1**）。可选 **`mtk-adapt-upgrade-platform-delta-table`** 作平台闸门。  
2. **柱 1**：从老树归纳器件 → 按下面 **二级分流** **`Read` 各 `mtk-adapt-template-device-*`**。  
3. **柱 2**：老树 dtsi 参数经 bridge / 专项 skill 映射后 → **`mtk-adapt-template-basic-charging-capability`** 及新树 `tc_charger` / `tc_pe5` 等落点。  
4. **柱 3**：在用户已 **口述（或可选提供输入表）** 明确柱 3 范围的前提下，按需 **`Read` `transsion-sunmao40-customization-features-adapt`**；**仅处理口述中「要做」** 的项；收尾按 router **「柱 3 输入与收口」** 与合并 skill **RULE-0**；升级专用 handoff 可后补。

### 专项闸门（仍须遵守）

- **`&pe5` / `mediatek,charger,pe5`（`mtk_pe50.dtsi`）→ 新树 `tc_pe5`（6.12 `transsion/tc_pe5.c`）**：热限 **`*_curlmt` 与 CP/dual 路径语义在老/新驱动不一致**（旧栈可对扣减量 ×2，新栈不 ×2）。凡迁移 **`mtk_pe50.dtsi` → `tc_pe5.dtsi`** 或核对 **dual/third CP 限流是否对齐**，执行者须 **`Read` `transsion-pe5-migrate-dual-cp-k612`**，再落盘；**不得**假设仅改 `compatible` 即等价。

**新侧路径纪律**（`project_full`、禁止全树 `grep` 反推路径等）以 **`mtk-adapt-upgrade-branch-orchestrator`** 正文 **路径解析纪律** 为准。

## 一级分流

先三选一：
- 器件适配
- 基本充电能力参数适配
- 客制化特性适配

## 二级分流（器件适配）

按器件类别路由：
- charger IC -> `mtk-adapt-template-device-charger-ic`
- PD IC -> `mtk-adapt-template-device-pd-ic`
- charge pump -> `mtk-adapt-template-device-charge-pump`
- gauge -> `mtk-adapt-template-device-gauge`

## 二级分流（器件外）

- 基本充电能力参数适配 -> `mtk-adapt-template-basic-charging-capability`（**LK** `tc_charger_lk.dtsi` 项目基线强约束见该 skill **「`tc_charger_lk.dtsi` 强约束」**：`fast-charge-voltage` 2.5 V、`ac-charger-*` 与 `ac-charger-input-*` 双 2 A、`non-std-ac-charger-current` 1.2 A、`temp-t4-threshold` 56 °C 等）
- 关机充电动画（KPOC 资源 / `TRAN_CHARGER_KPOC_ANIMATION` / `CUSTOM_TRAN_LOGO`）-> **`transsion-sunmao40-customization-features-adapt`**（**RULE-2** 或 **SM40-16** 二选一，见该 skill **RULE-0**）
- 开机工模 / 关机工模适配 -> **`transsion-sunmao40-customization-features-adapt`**（**RULE-3**）
- 其它客制化特性适配 -> **`transsion-sunmao40-customization-features-adapt`**（**RULE-1**；dtsi 客制化块注释另见 **RULE-4**）

## 最小输入契约

- 项目根路径
- 目标产品/平台
- 适配类别（器件 / 基本充电能力参数 / 客制化特性）
- 器件型号（器件适配时必填）
- 器件类别（器件适配时必填）
- 硬件连线摘要（器件适配时必填：bus、addr、irq、enable、电源）；若含 **TFCP / `protocol_ta.dtsi`**：在芯片平台基 dts（如 `mt6897.dts`）查 `protocol_ta` 所用 **`i2cN`** 的 **`scl-gpio-id` / `sda-gpio-id`**，并在 **kernel DWS + preloader `codegen.dws`** 为对应 GPIO 写 **`varName0`**：`TRAN_CHGPUMP_SCL_PIN`、`TRAN_CHGPUMP_SDA_PIN`（见 `mtk-adapt-template-device-charge-pump` 小节 1.6.1、`tran-projects-config-migrate-dtsi-dws` 中「protocol_ta.dtsi 与 TFCP I2C」）
- 参数清单（基本充电能力参数适配时必填）
- **柱 3 客制化特性（进入柱 3 落盘时必填）**：**对话里口述** 即可（规则见 **`transsion-sunmao40-customization-features-adapt`** **RULE-0「柱 3 口述输入」**）；可选附带 **`pillar3-customization-input.md`**。**仅用户明确「要做」** 的 RULE/SM40 进入本次柱 3 改码；不做且无工作量时说明 **「此项特性无适配工作量」**。
- 关机充电动画：若口述或表中 **RULE-2** / **SM40-16** **要做**，补充 `TRAN_CHARGER_KPOC_ANIMATION`、`CUSTOM_TRAN_LOGO`（品牌不确定时必填）
- 工模适配：若 **RULE-3** **要做**，补充工模类型（开机工模/关机工模）、进入条件、退出条件、是否影响充电链路
- 目标行为
- `tc_charger_lk.dtsi` 目标相对路径（建议用户直接给出）

## 输出契约

- 选中的模板技能
- 选择该路由的原因
- 缺失输入项（如有）
- 下一步执行清单
- 若未提供 dtsi 路径：给出按 6.1/6.12/6.6 推导的默认路径与 `vendor/` 回退结果
- **柱 3 收口（凡执行了柱 3）**：按合并 skill **RULE-0** 与上文 **「柱 3 输入与收口」**：提示用户 **未声明「要做」** 的 RULE/SM40（及可选输入表「否」摘要）；**仅提示、不实施**

## 边界

- 本技能不直接改文件。
- 如果请求是根因分析/流程分析，先回到已有分析类技能。
- 如果请求是基本能力参数适配，路由到 `mtk-adapt-template-basic-charging-capability`。
- 如果请求是关机充电动画 / KPOC 资源与 `CUSTOM_TRAN_LOGO`，路由到 **`transsion-sunmao40-customization-features-adapt`**（**RULE-2** 或 **SM40-16**，见该 skill **RULE-0**）。
- 如果请求是开机工模 / 关机工模适配，路由到 **`transsion-sunmao40-customization-features-adapt`**（**RULE-3**）。
- 如果请求是其它客制化特性适配，路由到 **`transsion-sunmao40-customization-features-adapt`**（**RULE-1**；`tc_charger` 客制化块注释见 **RULE-4**）。

---

## 修订记录

| 日期 | 摘要 |
|------|------|
| 2026-05-13 | 新增 **「新分支侧通用纪律」**：路径/搜索、三柱顺序、升级 handoff、强制 Read 表、硬件静态 vs 策略参数；**description** 同步摘要。 |
| 2026-05-14 | **柱 3**：**口述优先**；`pillar3-customization-input.md` 可选；冲突以对话为准。 |
| 2026-05-13 | **二级分流（器件外）**：指向 **`mtk-adapt-template-basic-charging-capability`** 中 **`tc_charger_lk.dtsi` 强约束**摘要（预充电压 2.5 V、AC 2 A、非标 1.2 A、`temp-t4` 56 °C）。 |
