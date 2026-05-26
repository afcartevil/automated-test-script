---
name: transsion-pe5-migrate-dual-cp-k612
description: >-
  柱 2 参数对齐：mtk_pe50 / &pe5 → tc_pe5.dtsi，按「老属性 → 新属性 → 转换策略」表迁移；含
  polling_interval、vbat_cv、idvchg_* 软启、ita/rcable_level（**单 CP 用老树 ita/rcable，双 CP 用 ita_dual/rcable_dual 写入新 ita/rcable**）、chg_time_max、vol_diff_*、
  cable_capability_level 等直拷项；**§1.0.1** `idvchg_level_multi`（老树 `ita_level[0]` + `ita_level_dual[0]`/7000）、`run_cp_cur`/`run_cp_recovery_gap`、`run_wls_*`（无线且支持才写）；热限 *curlmt（tta/tbat/tdvchg/tpcb/tmachine）在 dual/third
  下的 ×2 语义；tbat/tpcb 分档 *_level_def_*、*_curlmt_*、tpcb_recovery_area 及老树 // 注释解除；
  sys_power_level_def / sys_power_recovery_area 直拷、sys_power_curlmt 须 §1.1.1 对照驱动后再定是否随 CP 缩放；
  §1.9 supprot_multi_level_charging 默认、support_spec 用户填、vta/ita/vbus/rechg/project/min_ita/pe50_init/pe5_ffc_gap 默认向量；
  老树独有不同步；**§1.6 扩展无视项**；**§1.7** `ambient_temp`→`pid_chg`；**§1.8** ult-lt→ffc_level 电池表注释；
  禁×3、conversion_ratio 与 bridge 分工。
disable-model-invocation: true
funcType: "AI自动化适配"
category: "驱动"
---

# Transsion PE5：`mtk_pe50` → `tc_pe5`（柱 2 · 参数对照与转换策略）

## 调用场景（柱 2 · `tc_pe5` · 5.10 升级）

| 维度 | 约定 |
|------|------|
| **流程柱** | **`mtk-adapt-upgrade-branch-orchestrator` 柱 2**：老树 **`mtk_pe50.dtsi`** / **`&pe5`** 与新树 **`tc_pe5.dtsi`**（节点 **`tc_pe5`**）之间的 **参数对齐**。 |
| **内核代际** | **老：`kernel-5.10`**（`mtk_pe5.c`）；**新：`kernel_device_modules-*`（如 6.12）**（`transsion/tc_pe5.c`）。仅在新分支上改 `tc_pe5.dtsi`、**非自 5.10 升级**时，可参考下表规则，**不作强制 Read 本 skill**。 |
| **本 skill 不写的内容** | **`compatible` / phandle / `support_alg` 里 `&pe2`→`&tc_pe2`** 等节点级改名：**`transsion-charger-dtsi-driver-bridge`**。 |

**写入或审查 `tc_pe5.dtsi` 前**：柱 2 且 **5.10→新 KDM** 的 **`mtk_pe50`→`tc_pe5`** 任务须 **`Read` 本文件全文**（与 **`mtk-adapt-upgrade-branch-orchestrator` §13**、**`mtk-adapt-template-router`** 强制 Read 一致）。

---

## 在升级链路中的位置（柱 2）

| 上游 skill | 关系 |
|------------|------|
| **`mtk-adapt-template-router`** | 老分支→新分支，命中 **`&pe5`/`mtk_pe50`** 写 **`tc_pe5`** 时 **Read** 本 skill。 |
| **`mtk-adapt-upgrade-branch-orchestrator`** | **§13**：柱 2 闸门；**`mtk_pe50`→`tc_pe5（热限语义）`**。 |
| **`mtk-adapt-upgrade-inventory-checklist`** | **A.3**：清单命中 **`mtk_pe50.dtsi`** 且 **5.10→新 KDM** 时，handoff 注明已按本 skill 做 **柱 2 参数对照**。 |
| **`mtk-adapt-upgrade-platform-delta-table`** | **表 3**：热限不可盲拷的索引。 |

---

## 权威代码（对表时以各分支实树为准）

| 栈 | 典型路径 |
|----|-----------|
| **老** | `kernel-5.10/drivers/power/supply/mtk_pe5.c` |
| **新** | `kernel_device_modules-6.12/drivers/power/supply/transsion/tc_pe5.c`、`tc_pe5_pps_intf.c`、`tc_pe5_rfc_intf.c`、`tc_trancare.c` |

**驱动差异（所有下表策略的源头）**

| 项目 | 老 `mtk_pe5.c` | 新 `tc_pe5.c` / `tc_trancare.c` |
|------|----------------|----------------------------------|
| dual/third DVCHG 下从 `ita_lmt` 扣热限 | 对若干 `*_curlmt` 使用 **`2 * curlmt`** | **`ita_lmt - curlmt`**（**无** `2 *`，**无** `tried_dual_dvchg` 类分支） |
| 第三颗 CP | 仍走 **`2 * curlmt`**，**不是 `3 * curlmt`** | 同左列新栈：无 `3 *` 语义 |

因此：**多数 `*_curlmt` 属性名在 DTS 上老新相同**，但 **若要在新树上复现旧机 dual/third 下的有效扣减强度**，对「老栈里参与 `2 *` 扣减」的表，新表值常需 **×2**（见下表 **策略** 列）。

---

## 1. 主表：老分支参数 → 新分支参数 → 转换策略

**说明**

- **老侧来源**：`mtk_pe50.dtsi` 或板级 **`&pe5` / `mediatek,charger,pe5`** fragment 中 **与 `mtk_pe5.c` 绑定的属性名**（以老侧实树为准）。  
- **新侧落点**：`tc_pe5.dtsi` 中 **`tc_pe5` 节点**；属性名以新侧 **`tc_pe5.c` 的 `PE50_DT_VALPROP_*` / `pe50_parse_dt` 是否仍解析** 为准（迁前在目标树 **打开 `tc_pe5.c` 核对**）。  
- **逐格 / 逐元**：指 u32 数组中 **表示毫安级「扣减贡献」的正数格**；**0** 保持 **0**；**(-1)** 等**禁用/占位哨兵**一般 **不改动**；**`tmachine_curlmt_*` 中负数哨兵格**（如 **-2 / -3 / -4**）**不乘 2**。
- **单位**：`vbat_cv`、`start_vbat_*`、`idvchg_ss_*_vbat` 等在 **老树 `mtk_pe50` 与 PE5 绑定**里常见为 **mV 整数**（与 `mtk_pe5.c` / 项目惯例一致）。**直拷前**在目标 **`tc_pe5.c`** 确认 **OF 解析单位仍为 mV**；若新驱动改为 **µV**，则 **数值 ×1000** 再写入（或按 `pe50_parse_dt` 注释为准）。**`[REVIEW]`** 首次合入后核对节点 dump。

### 1.0 调度·CV·软启动·线检（老新 **属性名相同**，柱 2 **常与老树数值同源直拷**）

下列项在 **5.10 `mtk_pe50.dtsi` / `&pe5`** 与 **`tc_pe5` 节点** 中 **同名**居多，迁移策略为：**从老树逐属性拷贝到新 `tc_pe5.dtsi`**，**不**套用 §1.1 热限 **×2**（与 dual/third 语义无关）。**例外：`ita_level` / `rcable_level`** 见下 **「单 CP / 双 CP 选源」**，不得简单等同「整段直拷老树同名」。

**`ita_level` / `rcable_level`（新树仅一组属性名）**  
新 **`tc_pe5.dtsi` 只保留** **`ita_level`** 与 **`rcable_level`**（**无** `ita_level_dual` / `rcable_level_dual` 属性名）。老树若 **同时存在** 非 `_dual` 与 **`_dual`** 两套表，柱 2 **按项目 CP 拓扑** 决定 **数值** 从哪一套拷入新树 **`ita_level` / `rcable_level`**（两数组 **元素个数须一致**）：

| 项目 CP 拓扑 | 新树 `ita_level` 数值来源（老树） | 新树 `rcable_level` 数值来源（老树） |
|--------------|----------------------------------|-------------------------------------|
| **单 CP** | **`ita_level`** | **`rcable_level`** |
| **双 CP** | **`ita_level_dual`** | **`rcable_level_dual`** |

- **判定**：以 **BOM / 硬件（DVCHG 路数）/ 量产配置** 为准，必要时 **`Read` `mtk_pe5.c` / `tc_pe5.c`** 核对 dual 路径；疑难 **`[REVIEW]`** 产品。  
- **禁止**：双 CP 项目误用老树 **非 `_dual`** 表，导致 **ITA 档与线缆阻抗档** 与实机不一致。  
- **禁止**：在新 **`tc_pe5`** 节点 **再声明** 老树属性名 **`ita_level_dual` / `rcable_level_dual`**（见 **§1.6**：旧名 **不落盘**，仅作 **读侧** 数据源）。

| 老分支（`mtk_pe50` / `&pe5`） | 新分支（`tc_pe5`） | 转换策略 |
|------------------------------|-------------------|----------|
| `polling_interval` | `polling_interval` | **直拷**（周期/间隔单位以 **`mtk_pe5.c` / `tc_pe5.c`** 一致为准，常见 ms 量级整数）。 |
| `ta_cv_ss_repeat_tmin` | 同名 | **直拷**。 |
| `vbat_cv` | 同名 | **直拷**；单位见主表说明 **「单位」** 条（常见 mV）。 |
| `start_vbat_max`、`start_vbat_min` | 同名 | **直拷**；同上 **mV / µV** 须与新驱动一致。 |
| `idvchg_term` | 同名 | **直拷**（截止/阈值类，单位以老新驱动同一属性解析为准，常见 mA 或工程约定整数）。 |
| `ita_level` | 同名 | **见上「单 CP / 双 CP 选源」**；整数组写入；**不**做 §1.1 ×2。 |
| `rcable_level` | 同名 | **见上「单 CP / 双 CP 选源」**；与 **`ita_level` 档位数对齐**。 |
| `idvchg_ss_init`、`idvchg_ss_step`、`idvchg_ss_step1`、`idvchg_ss_step2` | 同名 | **直拷**（软启步进，单位以驱动为准）。 |
| `idvchg_ss_step1_vbat`、`idvchg_ss_step2_vbat` | 同名 | **直拷**；电压阈值见 **「单位」** 条（常见 mV）。 |
| `ta_blanking` | 同名 | **直拷**。 |
| `chg_time_max` | 同名 | **直拷**（常见 s 或驱动约定）。 |
| `vol_diff_gap` | 同名 | **直拷**。 |
| `cable_capability_level` | 同名 | **直拷**整数组。 |
| `vol_diff_level` | 同名 | **直拷**整数组。 |

**与项目禁同步清单的关系**：若项目 **`charging_migration_rules`** 等文档声明 **某属性禁止从老树同步**（例如 `start_soc_*`、`judge_cable` 等），**以项目闸门为准覆盖**上表「直拷」。**`ambient_temp`** **不**在 `tc_pe5` 直拷，见 **§1.7**。

### 1.0.1 新树专有：`idvchg_level_multi` / `run_cp_*` / `run_wls_*`（由老树派生，**非**整段直拷）

下列属性常见于 **新 `tc_pe5.dtsi`**，老树 **`mtk_pe50` / `&pe5`** 往往 **无同名项**；柱 2 按 **下表算术** 从老树 **`ita_level` / `ita_level_dual` / `idvchg_term`** 生成。**合入前 `Read` `tc_pe5.c`**，确认 **`PE50_DT_VALPROP_*`** 仍解析这些属性名。

| 新分支（`tc_pe5`） | 转换策略 |
|-------------------|----------|
| **`idvchg_level_multi`** | 写 **四元组** `<L0 L1 L2 L3>`：**L0** = 老树 **`ita_level`** 数组 **第 1 个元素**（**始终**读老树 **非 `_dual`** 的 **`ita_level`**，与 §1.0 按单/双 CP 选写入新树 **`ita_level` 整表** 的规则 **无关**——此处固定用 **`ita_level[0]`** 作第一档）。**L1** = 老树 **`ita_level_dual`** 第 1 个元素；若老树 **无** `ita_level_dual`、或数组 **缺项/为空**，则 **L1 = 7000**。**L2 = L3 = L1**。单位与老树 **`ita_level`** 格一致（常见 **mA**）。 |
| **`run_cp_cur`** | 写 **四元组** `<0 R1 R2 R3>`：**R1** = **`idvchg_term` × 5**；**R2** = **`min(idvchg_term × 7, 4250)`**（与 **4250** 取较小者，单位与 **`idvchg_term`** 一致，常见 **mA**）；**R3 = R2**（第四元与第三元相同）。**`idvchg_term`** 取 **老树已按 §1.0 直拷到新树** 的数值（同一解析单位下做算术）。 |
| **`run_cp_recovery_gap`** | **固定** `<0 500 750 1000>`，不按老树逐项拷贝。 |
| **`run_wls_cp_cur`** | **固定** `<0 3000 6000 10000>`。**仅当** 项目 **支持无线充**（BOM / `support_alg` / 无线供电链路已启用，且 **`tc_pe5.c` 仍解析**）时写入；**不支持无线则整条省略**，勿占位。 |
| **`run_wls_cp_recovery_gap`** | **固定** `<0 200 400 600>`；**同上**，不支持无线则 **不写**。 |

**注意**：若老树 **`ita_level`** 缺失或首元无法取值，**`[REVIEW]`** 产品/硬件后再填 **L0**，勿盲填 0 冒充有效档。

### 1.1 热限流数组（老新 **属性名相同**，策略在 **数值**）

**「按 CP 数量 ×2」在本 skill 中的含义（与 `mtk_pe5.c` 一致）**

- 旧栈在 **dual / third DVCHG** 路径下，对若干 **`*_curlmt`** 从 `ita_lmt` 扣减时使用 **`2 * curlmt`**（系数写死为 **2**，**不是**「CP 颗数 N 就 ×N」）。新栈 **`tc_pe5.c`** 为 **`ita_lmt - curlmt`**（**无** `2 *`）。  
- 因此：柱 2 若需 **对齐旧机在双/多路 DVCHG 已量产的热限强度**，对 **参与旧栈该 `2 *` 扣减链** 的 `*_curlmt` 表，新表常见 **`table_new ≈ 2 × table_old`**（仅对 **正数毫安级限流格**；**0**、**(-1)** 等哨兵、**`tmachine` 负哨兵格** 规则同主表 **「说明」**）。  
- **第三颗 CP**：旧代码仍用 **`2 * curlmt`**，**没有 `3 *`** → **不得**因「三颗 CP」对 `*_curlmt` 再乘 3（见 **§2**）。  
- **单路 DVCHG**：旧栈为 **`ita_lmt - 1×curlmt`** → **不宜**对上述 `*_curlmt` 盲 ×2。

**档位定义与回滞（不做 ×2）**：**`tta` / `tbat` / `tdvchg` / `tpcb`** 的 **`*_level_def`、`*_level_def_*`、`*_recovery_area`** 描述 **温度档位 / 回滞区**，**不**参与 `2 * curlmt` 扣减语义 → **从老树直拷**到新树，**禁止**对整表做 CP ×2。**`tswchg_level_def` / `tswchg_curlmt` / `tswchg_recovery_area`** 见 **§1.6**（默认 **不同步**）。

**老树注释行（`//` / 块注释）— 解除后同步**  
若老 `mtk_pe50` / overlay 中 **`tpcb_level_def_N` / `tpcb_curlmt_N`** 或 **`tbat_level_def_N` / `tbat_curlmt_N`** 等 **整行仅以注释关闭**（常见 **`//tpcb_level_def_1`**）：柱 2 写入新 **`tc_pe5.dtsi` 时须去掉注释**，作为 **可编译的正式属性** 落盘；**`*_level_def*`** 数值 **直拷**；**`tpcb_curlmt_*` / `tbat_curlmt_*`** 仍按本节与 **`tta_curlmt`** 相同的 **dual/third 路径下 ×2**（口语「按 CP」含义见本节前段；**非**×3；**单路**不盲 ×2）。若工程上确需废弃某一档，用 **`status`**、删属性或项目约定表达，**不要**在新树长期保留「只活在注释里的半套档」。

| 老分支（5.10 `mtk_pe50` / `&pe5`） | 新分支（`tc_pe5`） | 转换策略 |
|-----------------------------------|-------------------|----------|
| `tta_level_def` | `tta_level_def` | **直拷**整数组（℃ 档位边界，**不**×2）。 |
| `tta_recovery_area` | `tta_recovery_area` | **直拷**。 |
| `tta_curlmt` | `tta_curlmt` | **量产路径为 dual/third DVCHG、需对齐旧机有效热限时**：新表 **≈ 老表 ×2**（正数限流格；哨兵格见主表 **「说明」**）。**仅单路** 见本节前段，**不宜**盲 ×2。 |
| `tbat_level_def` | `tbat_level_def` | **直拷**（无分档后缀时的单表）。 |
| `tbat_level_def_0`、`tbat_level_def_1`、`tbat_level_def_2` | 同名 | **直拷**整数组（**不**×2）；老树有则逐档写入；若老树某档仅 **`//` 注释**，见上 **「老树注释行」**。 |
| `tbat_recovery_area` | `tbat_recovery_area` | **直拷**。 |
| `tbat_curlmt` | `tbat_curlmt` | **同 `tta_curlmt`**（无 `_0/1/2` 后缀的单表）。 |
| `tbat_curlmt_0`、`tbat_curlmt_1`、`tbat_curlmt_2` | 同名 | **同 `tta_curlmt`**：dual/third 热限对齐时正数格 **×2**；单路不盲 ×2。 |
| `tdvchg_level_def` | `tdvchg_level_def` | **直拷**整数组（**不**×2）。 |
| `tdvchg_recovery_area` | `tdvchg_recovery_area` | **直拷**。 |
| `tdvchg_curlmt` | `tdvchg_curlmt` | **同 `tta_curlmt`**。 |
| `tpcb_level_def_0`、`tpcb_level_def_1`、`tpcb_level_def_2` | 同名 | **直拷**（**不**×2）。老树 **`tpcb_level_def_1` / `tpcb_curlmt_1`** 等若以 **`//`** 注释，新树 **解除注释** 后同上 **直拷**。 |
| `tpcb_curlmt_0`、`tpcb_curlmt_1`、`tpcb_curlmt_2` | 同名 | **同 `tta_curlmt`**：dual/third 下正数格 **×2**；**解除注释** 后对该档同样 ×2。 |
| `tpcb_curlmt`（无 `_0/1/2` 后缀时） | 同名 | **同 `tta_curlmt`**。 |
| `tpcb_recovery_area` | `tpcb_recovery_area` | **直拷**。 |
| `tmachine_curlmt`、`tmachine_curlmt_0`～`tmachine_curlmt_3` | 同名 | **仅对正数限流格**可 **×2** 与旧 dual/third 对齐；**哨兵/负格不乘**；疑难 **`[REVIEW]`** 旧 `mtk_pe5.c`。 |

### 1.1.1 `sys_power_*`（老树可同步；**是否**按 CP / dual 改表须 **Read 驱动核实**）

与 **`tta_curlmt` 等「`ita_lmt - 2*curlmt` → 新栈 `ita_lmt - curlmt`」** 的热限链 **不是同一套语义**：**禁止**不经核对就把 **§1.1 的 ×2 模板** 机械套到 **`sys_power_curlmt`**。

| 老分支（`mtk_pe50` / `&pe5`） | 新分支（`tc_pe5`） | 转换策略 |
|------------------------------|-------------------|----------|
| `sys_power_level_def` | `sys_power_level_def` | **默认直拷**整数组（功率档位边界，**不**套用 `tta_curlmt` 的 ×2）。若新 **`tc_pe5.c` / `tc_trancare.c`** 要求 **长度、单位或档数** 与旧不同，按新驱动改表并标 **`[REVIEW]`**。 |
| `sys_power_recovery_area` | `sys_power_recovery_area` | **直拷**。 |
| `sys_power_curlmt` | `sys_power_curlmt` | **可从老树同步为新树初值**。是否在 **dual / third DVCHG** 或 **多 CP 预算** 下需对正数格做 **等比缩放（可能含 ×2，也可能为其它系数或保持直拷）**，**必须**在 **`mtk_pe5.c`** 与 **`tc_pe5.c`、`tc_trancare.c`** 中 **确认该表在 ITA / 功率 min 链上的消费方式** 后再定；**吃不准时** 保持老树数值并 **`[REVIEW]`** 实机/仪表。 |

### 1.1.2 保护与 TA 能力（可参考老树；**是否**随 CP / dual 缩放须 **Read 驱动**）

下列属性在 **`mtk_pe50` / `&pe5` → `tc_pe5`** 上 **多为同名**；柱 2 **以老树为参考值**合入时，**默认可先直拷**，但 **与 `tta_curlmt` 热限 ×2（§1.1）不是同一规则**——**禁止**不经核对就把 **§1.1 的 `*_curlmt` ×2 模板** 套到本组。**是否**与 **CP 路数 / dual DVCHG / ITA 合成** 成比例，须在 **`mtk_pe5.c` / `tc_pe5.c`（及 `tc_pe5_pps_intf.c` 等）** 查清 **消费点** 后再改表；**吃不准**保持老树值并 **`[REVIEW]`**。

| 老分支（`mtk_pe50` / `&pe5`） | 新分支（`tc_pe5`） | 转换策略 |
|------------------------------|-------------------|----------|
| `ifod_threshold` | 同名 | **参考老树直拷**；量纲以 **`tc_pe5.c`** 为准；若与 **多路 ITA/CP** 比较链相关，是否与 **CP 数** 成比例 **`[REVIEW]`** 驱动。 |
| `rsw_min` | 同名 | **参考老树直拷**；同上。 |
| `ircmp_rbat`、`ircmp_vclamp` | 同名 | **参考老树直拷**；IR 补偿是否与 **dual/CP** 路径重标定，**`[REVIEW]`** 新栈公式。 |
| `vta_cap_min`、`vta_cap_max` | 同名 | **参考老树直拷**（常见 **mV**）；与 **TA 电压能力/协议** 绑定，**非** §1.1 热限 ×2；dual 下名义能力是否重写由 **硬件 + 新 PE5/PD 栈** 定，`[REVIEW]`。 |
| `ita_cap_min` | 同名 | **参考老树直拷**（常见 **mA**）；是否与 **并联 CP 电流预算** 成比例须 **Read** 新栈对该属性的使用方式；**吃不准**先直拷 + `[REVIEW]`。 |
| `project_power` | 同名 | **参考老树直拷**；与 **`sys_power_*` 档位** 或 **功率 min** 联动时，是否与 **多 CP** 有关，**交叉 Read** **`mtk_pe5.c`/`tc_pe5.c`** 与 **§1.1.1**。 |
| `allow_not_check_ta_status` | 同名 | **直拷**（整型/布尔语义以新驱动为准）；语义变更 **`[REVIEW]`**。 |
| `vbat_threshold` | 同名 | **参考老树**；**务必**在 **`tc_pe5.c`** 确认 **单位（mV / µV）** 与主表 **§1.0「单位」** 一致。**勿**与板级 **`tc_charger.dtsi`** 里 **`support_alg` 子节点** 的 **`vbat_threshold`（µV 迁移）** 混用不同节点、不同单位。 |
| `idvchg_pps_term` | 同名 | **参考老树直拷**（常见 **mA** 类截止）；与 **PPS** 及 **CP 路数** 的关系以 **`tc_pe5_pps_intf.c`** / `tc_pe5.c` 为准 **`[REVIEW]`**。 |

**新树为向量、老树为标量或缺项时**：**`vta_cap_min` / `vta_cap_max` / `ita_cap_min` / `vbus_max_ovp`** 可采用 **§1.9** **cl6k_h898 默认五元组**；**`support_spec`** **须用户填写**（§1.9），**不得**留未定义占位合树。

### 1.1.3 `support_ta` 字符串转义（老分支 token → 新分支合法串）

`support_ta` 为 **字符串列表**（如 **`"tfcp_adapter", "pd_adapter", ..."`**），**老新 token 字面量、集合、弃用项** 可能不同，**禁止**假定整串 **无修改** 即可被新 **`tc_pe5.c`** 解析。

**执行步骤**

1. **摘录**老树 **`support_ta`** 全文（含引号与逗号分隔）。  
2. **`Read` `mtk_pe5.c`**：按 **strcmp / match 表** 记录 **每个旧 token 的语义**（如 RFC、TFCP、PD、HVDCP30 等，以老代码为准）。  
3. **`Read` `tc_pe5.c` / `pe50_parse_dt`**（及 **`tc_pe5_rfc_intf.c`** 等 TA 后端注册处）：列出 **新栈仍接受的 token 字符串** 与 **已删除/合并名称**。  
4. 在会话中输出 **逐 token 映射表**：`OLD:"..."` → `NEW:"..."` 或 **`DROP`**（新栈无等价且产品确认不启用）。  
5. 写回新 DTS，仅保留 **步骤 3 已验证可解析** 的 token，例如：  
   `support_ta = "NEW_A", "NEW_B";`  
6. 常与 **`support_spec`、`default_spec`、`vbus_max_ovp`** 等 **联动修改**；仍以 **`tc_pe5.c`** 合法集为准，本 skill **不**维护完整枚举表。**`support_spec`** 见 **§1.9**（**须用户填写**，本 skill 不给数值）。

**与 CP 的关系**：`support_ta` 描述 **启用的 TA 后端类型**，**不是** `*_curlmt` 毫安表；**不因** dual/third 对字符串本身做 **×2**；若某后端在 **多 CP** 下才允许启用，由 **步骤 2～3 的代码 + 产品策略** 决定是否在映射表中 **保留或 DROP**。

### 1.2 无线 PE5 热限（老新 **属性名相同**，**不经由 §1.1 的 ×2**）

| 老分支 | 新分支 | 转换策略 |
|--------|--------|----------|
| `wireless_tbat_curlmt` | `wireless_tbat_curlmt`（若新树解析） | 旧栈无线分支对这些表为 **单次扣减（无 `2 *`）** → 新表通常 **与原老树数值同量级拷贝**，**不要**按有线 dual CP 再 ×2。 |
| `wireless_tpcb_curlmt` | 同名 | 同上。 |
| `wireless_tmachine_curlmt` | 同名 | 同上。 |

### 1.3 不按「热限 dual/third ×2」处理的同名参数（**拷贝或单独建模**）

| 老分支 | 新分支 | 转换策略 |
|--------|--------|----------|
| `sys_power_level_def`、`sys_power_curlmt`、`sys_power_recovery_area` | 同名 | 见 **§1.1.1**（**不得**套用 §1.1 `tta_curlmt` 盲 ×2）。 |
| `ifod_threshold`、`rsw_min`、`ircmp_rbat`、`ircmp_vclamp`、`vta_cap_min`、`vta_cap_max`、`ita_cap_min`、`project_power`、`allow_not_check_ta_status`、`vbat_threshold`、`idvchg_pps_term` | 同名 | 见 **§1.1.2**；**`support_ta`** 见 **§1.1.3**。 |
| `ita_level` | 同名 | **不乘 2**；**数值来源**见 **§1.0**（单 CP / 双 CP 选老树 `ita_level` 或 `ita_level_dual`）；**禁止**套用 §1.1 ×2。 |
| `rcable_level` | 同名 | 同上；**`rcable_level` / `rcable_level_dual`** 选源见 **§1.0**。 |
| `tswchg_curlmt`、`idvchg_step` 等 | — | **不同步**，见 **§1.6**。 |
| `dv2_ffc_*`（老，**不含** §1.8 **ult-lt 专族**） / `step_ffc_*`（新常见） | `step_ffc_*`、`batX_step_ffc_level_*` 等 | **FFC 电池分段**，与 `*_curlmt` ×2 **无关**；须对照 **`tc_pe5.c` / `pe50_parse_dt`** **单独迁移**，禁止套用 §1.1 热限 ×2。**`dv2_ffc_ult_lt_*` / `dv2_ffc_ult_lt_level`** 见 **§1.8**。 |
| `ibat_max` | 若新节点 **未解析** 则无对应写入 | **勿**强行添加；含义亦非热限 ×2。 |
| `idvchg_level_multi`、`run_cp_cur`、`run_cp_recovery_gap`、`run_wls_cp_cur`、`run_wls_cp_recovery_gap` | 新树专有（老树常 **无** 同名） | **§1.0.1**：由老树 **`ita_level`/`ita_level_dual`/`idvchg_term`** 派生或 **固定向量**；**勿**套用 §1.1 `*_curlmt` ×2。 |

### 1.4 DVCHG 保护 · 变比（**语义与 `tta_curlmt` ×2 独立**）

| 老分支（实现/习惯） | 新分支 | 转换策略 |
|--------------------|--------|----------|
| 旧 `mtk_pe5.c` 中常见 **`2 * idvchg_cc`** 等 **固定倍率** 写进保护逻辑 | 新 `tc_pe5.c` **`pe50_set_dvchg_protection`** 使用 **`conversion_ratio * idvchg_cc`** | 在新树 **`tc_pe5` 节点** 配置 **`conversion_ratio`** 以表达 **CP 电流变比/保护**，**不是**「CP 颗数」，也 **不是** 对 §1.1 各表再乘一遍 2。按硬件与目标 `tc_pe5.c` 填；与 §1.1 **分开决策**。 |

### 1.5 节点与句柄（本 skill 只列策略边界）

| 老分支 | 新分支 | 转换策略 |
|--------|--------|----------|
| `compatible = "mediatek,charger,pe5"`，**`charger` / `gauge` 等 phandle** | `compatible` 为 **`tc_pe5`**（以新 `of_match` 为准），**重连 `tc_chgtype`、gauge 等** | **属 bridge + 板级整理**，按 **`transsion-charger-dtsi-driver-bridge`** 与项目 `tc_pe5.dtsi` 范例改 phandle，**不**在本表展开逐字段。 |

### 1.6 老树独有 / 新 `tc_pe5` **不承接** — **不同步**（勿写入新 DTS）

下列属性常见于 **5.10 `mtk_pe50` / `&pe5`**。前段为 **新 `tc_pe5` 不解析、勿拷贝**；后段为项目约定 **「无视」— 新分支不使用**，柱 2 **勿**写入 **`tc_pe5.dtsi`**。草稿中若残留应 **删除**（与 **`charging_migration_rules`** 等可互引）。

| 老分支（`mtk_pe50` / `&pe5`） | 新分支（`tc_pe5`） | 转换策略 |
|------------------------------|-------------------|----------|
| `tswchg_level_def` | **无对应 / 不解析** | **不同步**；新 DTS **不写**。 |
| `tswchg_curlmt` | **无对应 / 不解析** | **不同步**；**禁止**套用 §1.1 热限 ×2 后写入。 |
| `tswchg_recovery_area` | **无对应 / 不解析** | **不同步**。 |
| `judge_vol_diff` | **无对应 / 不解析** | **不同步**（老侧多为 bool/空属性形态，以老树为准）。 |
| `swchg_aicr`、`swchg_ichg`、`swchg_aicr_ss_init`、`swchg_aicr_ss_step`、`swchg_off_vbat`、`force_ta_cv_vbat` | **无对应 / 不解析** | **不同步**；新侧 **SWCHG 相关策略** 若在 **其它节点 / 其它子系统** 承接，**不在本 skill 的 `tc_pe5` 节点内** 用老树同名属性凑数。 |
| `ita_level_dual`、`rcable_level_dual` | **不**以旧名写入 `tc_pe5` | **不作为** 新树 **属性名** 落盘；**双 CP** 时其 **数值** 并入新 **`ita_level` / `rcable_level`**，见 **§1.0**「单 CP / 双 CP 选源」。**单 CP** 项目 **勿**误拷 dual 表。 |
| `idvchg_step` | **无对应 / 不解析** | **不同步**；与 **`idvchg_ss_*`** 并存于老树时，仅迁 **§1.0** 已列 **`idvchg_ss_*`**。 |
| `dv2_try_dual_threshold` | — | **无视**；新分支 **不使用**，**勿**写入 **`tc_pe5`**。 |
| `cv_reduce_step` | — | **无视**。 |
| `rechg_ab_h`、`rechg_ab_l` | — | **无视**。 |
| `dv2_ab_dev` | — | **无视**。 |
| `lcd_on_ita` | — | **无视**。 |
| `ult_lt_vbat_cv`、`dv2_support_ult_lt` | — | **无视**；新分支 **不使用**（与 **§1.8** **ffc_level 电池表路径**区分：ult-lt 老表 **不**直拷进 `tc_pe5`）。 |
| `judge_cable` | — | **无视**。 |
| `start_soc_min`、`start_soc_max` | — | **无视**；新分支 **不使用**。 |

**例外**：若后续某版本 **`tc_pe5.c` 重新解析** 上表某属性，以 **该版本 `Read tc_pe5.c` + 项目变更说明** 为准 **单独开表**，**不**自动推翻本 skill 默认「不同步」。

### 1.7 `ambient_temp`（老树 **`&pe5` / `mtk_pe50`**）→ 新树 **`pid_chg`**（**不写进 `tc_pe5`**）

| 老分支（`mtk_pe50` / `&pe5`） | 新分支 | 转换策略 |
|------------------------------|--------|----------|
| `ambient_temp` | **`pid_chg` 节点**（`compatible = "tc,pid_chg_algo"` 等，以目标树为准） | **禁止**把老树 **`ambient_temp`** 继续放在 **`tc_pe5.dtsi`**。柱 2 将 **环境温度分档 / 数组** 迁入 **`tc_charger` 域 `pid_chg`**，与 **`ambient_temp`、`target_temp_array`**（及 **`power_level` 五档** 等）的语义对齐见 **`transsion-charger-dtsi-driver-bridge`**、**`mtk-adapt-upgrade-branch-orchestrator` 路径纪律 §9**、**`mtk-adapt-template-basic-charging-capability`** 中 **`pid_chg`** 章节（含 **`tran,pid_chg_algo`→`tc,pid_chg_algo`** 等）。本 skill **仅声明边界**：该项 **不属于** **`tc_pe5` 节点** 的迁移产物。 |

### 1.8 老树 **`dv2_ffc_ult_lt_*` / `dv2_ffc_ult_lt_level`** → 新树 **`ffc_level`**（**电池表生成**）

下列 **ultimate-low（ult-lt）温区 FFC** 相关属性（含 **`dv2_ffc_ult_lt_level`**、**`dv2_ffc_vbat_*_ult_lt_*`、 `dv2_ffc_ibat_*_ult_lt_*`** 等 **整族**）：

| 老分支 | 新分支 | 转换策略 |
|--------|--------|----------|
| **`dv2_ffc_ult_lt_*` 整块**、`dv2_ffc_ult_lt_level` | **`ffc_level`** 及新栈 **`step_ffc_*` / `batX_step_ffc_level_*`** 等（以 **`tc_pe5.c` / 项目电池表模板** 为准） | **禁止**从 **`mtk_pe50.dtsi`** 对 ult-lt 表 **机械直拷** 填数。柱 2 生成 **`tc_pe5.dtsi`**（或合并 fragment）时，在 **ffc_level / FFC ult-lt 占位处** 增加 **固定注释**，明确 **数值来源为电池表**，例如：  
`/* ffc_level（含原 dv2_ffc_ult_lt_*）：以下由电池表生成，勿从 mtk_pe50 直拷 */`  
（项目可统一措辞，须同时出现 **「ffc_level」** 与 **「电池表」** 语义。）  
实际 **分段 V/I、档位数** 由 **电池表 / 电芯规格** 产出；本 skill **不**展开 FFC 算法。 |

### 1.9 新 `tc_pe5` 生成默认（**`cl6k_h898` / `tc_pe50.dtsi` 基线**）

用于柱 2 **首次生成**或 **补全**新分支 **`tc_pe5.dtsi`** 时尚无项目独立基线的 **占位默认值**（与 **`kernel_device_modules-6.12/.../charge/cl6k_h898/tc_pe50.dtsi`** 对齐）。**其它项目**若偏离本表，须在会话中 **显式声明** 并 **`[REVIEW]`**。

| 新分支属性 | 策略 | 默认 / 约定 |
|------------|------|----------------|
| **`supprot_multi_level_charging`** | **新分支直接默认写上** | 以 **空属性**（boolean）出现在 **`&pe5` / `tc_pe5`** 中即可。**拼写为 `supprot_`**，合入前 **`Read` `tc_pe5.c`** 确认属性名未变更。 |
| **`support_spec`** | **须用户自行填写** | 本 skill **不提供**默认 `<...>` 向量。柱 2 产出时在属性上方留注释 **`/* USER: support_spec — 须与 support_ta、vta_cap_* 档位数一致 */`** 或 **由用户补全** 后再合树。 |
| **`vta_cap_min`** | 无项目基线时 **采用下列默认** | `<6800 6800 6800 6800 4000>` |
| **`vta_cap_max`** | 同上 | `<30500 20500 20500 10500 7000>` |
| **`ita_cap_min`** | 同上 | `<1000 1000 1000 1000 1000>` |
| **`vbus_max_ovp`** | 同上 | `<33000 20500 20500 11000 7000>` |
| **`rechg_tbat_high`** | 同上 | `<44>` |
| **`rechg_tbat_low`** | 同上 | `<12>` |
| **`project_pwr_ratio`** | 同上 | `<70>` |
| **`min_ita_gap`** | 同上 | `<10>` |
| **`ita_stable_cnt`** | 同上 | `<20>` |
| **`pe50_vta_init`** | 同上 | `<5300>` |
| **`pe50_ita_init`** | 同上 | `<3000>` |
| **`pe5_ffc_gap`** | 同上 | `<20 20 20 20 20 20>` |

**可复制片段（不含 `support_spec` 数值）**：

```dts
	supprot_multi_level_charging;
	/* support_spec：须用户填写，与 support_ta、下列向量列数一致 */
	vta_cap_min = <6800 6800 6800 6800 4000>;
	vta_cap_max = <30500 20500 20500 10500 7000>;
	ita_cap_min = <1000 1000 1000 1000 1000>;
	vbus_max_ovp = <33000 20500 20500 11000 7000>;
	rechg_tbat_high = <44>;
	rechg_tbat_low = <12>;
	project_pwr_ratio = <70>;
	min_ita_gap = <10>;
	ita_stable_cnt = <20>;
	pe50_vta_init = <5300>;
	pe50_ita_init = <3000>;
	pe5_ffc_gap = <20 20 20 20 20 20>;
```

**与 §1.1.2 / §1.1.3 的关系**：上表为 **新树首版默认**；若 **`mtk_pe50` 老树** 对 **`vta_cap_*` 等为标量** 而须 **语义对齐**，仍以 **§1.1.2** 的 **Read 驱动** 纪律为准；**`support_ta`** 仍按 **§1.1.3** 转义；**`support_spec`** **始终** 用户定稿。

---

## 2. 禁则（与主表策略一致，便于速查）

- **×3**：旧 `mtk_pe5.c` 在 **third DVCHG** 下仍用 **`2 * curlmt`**，**没有** `3 * curlmt` → 迁移时 **不得**因「三颗 CP」对 `*_curlmt` 做 ×3。  
- **单路 DVCHG 项目**：旧栈热限为 **`ita_lmt - 1×curlmt`**，新表 **不宜**默认按 §1.1 对全表 ×2。  
- **合入前**：在目标仓库 **`Read` `tc_pe5.c`**，确认 **`PE50_DT_VALPROP_*` / 属性名** 与下表老新列 **仍一致**；若新驱动改名，以 **新代码** 为准更新 **新分支** 列。  
- **§1.6**：**`tswchg_*`、`swchg_*`、`judge_vol_diff`、`idvchg_step`** 及 **`dv2_try_dual_threshold`…** 等 **勿写入**新 **`tc_pe5`**。**`ita_level_dual` / `rcable_level_dual` 旧名勿落盘**；数值合并见 **§1.0**。  
- **`ambient_temp`**：**勿**写入 **`tc_pe5`**，迁 **`pid_chg`**，见 **§1.7**。  
- **`dv2_ffc_ult_lt_*` / `dv2_ffc_ult_lt_level`**：**勿**从老树机械抄数；**ffc_level** 段按 **§1.8** 用 **电池表** 并加注释。  
- **`sys_power_curlmt`**：**勿**不经 **§1.1.1** 核对即套用 **`tta_curlmt` / `tpcb_curlmt`** 的 dual/third **×2** 模板。  
- **`support_ta`**：**勿**把老树 **整串字面量** 无 **§1.1.3** 映射表即写入新 DTS。  
- **`idvchg_level_multi` / `run_cp_cur`**：**勿**用新树 **`ita_level` 整表首元** 代替 §1.0.1 规定的 **老树非 dual `ita_level[0]`** 与 **`ita_level_dual[0]`/7000** 拼装逻辑；**`run_cp_cur`** 须在 **`idvchg_term`** 直拷之后再算。

---

## 3. 落地顺序（Agent）

1. 打开 **新** `tc_pe5.c`，列出仍解析的 **PE5 设备树属性名**。  
2. **§1.0**：将 **`polling_interval`、`vbat_cv`、`idvchg_term`、`idvchg_*` 软启、`chg_time_max`、`vol_diff_*`、`cable_capability_level` 等** 从老树 **直拷**到 `tc_pe5`；**`ita_level` / `rcable_level`** 按 **§1.0「单 CP / 双 CP 选源」** 从老树 **`ita_level`/`rcable_level`** 或 **`ita_level_dual`/`rcable_level_dual`** 写入（**不含** **`ambient_temp`**，见 **§1.7**；核对 **mV vs µV** 见主表 **「单位」**）。  
2a. **§1.0.1**：按 **老树** **`ita_level`/`ita_level_dual`** 生成 **`idvchg_level_multi`**；在 **`idvchg_term`** 已从老树 **直拷落盘**（或迁移会话中已确定其数值）后，计算 **`run_cp_cur`** 并写入 **`run_cp_recovery_gap`** 固定向量；若项目 **支持无线**，再写 **`run_wls_cp_cur`、`run_wls_cp_recovery_gap`**，否则 **省略** 两条无线属性。  
2b. **`ambient_temp`**：按 **§1.7** 迁入 **`tc_charger` 域 `pid_chg`**（见 **bridge §9**），**勿**留在 **`tc_pe5`**。  
3. 从 **老** `mtk_pe50.dtsi` / `&pe5` 取热限等源表，按 **§1.1～§1.4** 填 **新** `tc_pe5.dtsi`：**`tbat_level_def_*` / `tbat_curlmt_*`、`tpcb_level_def_*` / `tpcb_curlmt_*` / `tpcb_recovery_area`** 与 **`tta_*`** 同表；老树 **`//`** 注释的 **`tpcb_*` / `tbat_*` 分档行** 须 **解除注释** 再 **level 直拷、curlmt 按 dual/third ×2**（单路不盲 ×2）。  
4. **`sys_power_*`** 见 **§1.1.1**；**`ifod_threshold`…** 见 **§1.1.2**；**`support_ta`** 见 **§1.1.3**。**§1.9**：写入 **`supprot_multi_level_charging`** 及 **`vta_cap_*` 等默认向量**；**`support_spec`** 留 **用户填写**。**FFC（含 ult-lt）**：一般 **`dv2_ffc_*`→`step_ffc_*`** 见 **§1.3**；**`dv2_ffc_ult_lt_*` / `dv2_ffc_ult_lt_level`** 按 **§1.8** 在 **`tc_pe5.dtsi` 标注释「ffc_level 由电池表生成」**，**勿**从 **`mtk_pe50`** 直拷数值。**`conversion_ratio`** 见 **§1.4**；**§1.6 不同步/无视项** 从草稿 **删除**。**禁止**把 §1.6 项套用 `tta_curlmt` 的 ×2；**禁止**不经 §1.1.1 核对把 **`sys_power_curlmt`** 当 **`tta_curlmt`** 盲 ×2。  
5. 在修改后的 `tc_pe5.dtsi` 或项目 **`docs/tc_pe5.dtsi`** 中可注释：**「热限表已对 dual/third parity 做 ×2」**（若采用 §1.1），便于与「未加工 MTK 原表」区分。

---

## 4. 修订记录

| 日期 | 摘要 |
|------|------|
| 2026-05-13 | **调用场景** 柱 2 / 5.10 升级 / `tc_pe5`；**正文** 以 **老分支参数 → 新分支参数 → 转换策略** 主表（§1.0～**1.9**）重写，**description** 与 **§2 禁则、§3 落地顺序** 配套。 |
| 2026-05-13 | **§1.0**：**`ita_level`/`rcable_level`** 按项目 **单 CP / 双 CP** 从老树 **`ita_level`/`rcable_level`** 或 **`ita_level_dual`/`rcable_level_dual`** 选源写入（新树 **不落盘** `*_dual` 名）；§1.3/§1.6/§2/§3/description 已对齐。 |
| 2026-05-13 | **§1.6** 增 **无视** 行（`dv2_try_dual_threshold`、`cv_reduce_step`、`rechg_ab_*`、`dv2_ab_dev`、`lcd_on_ita`、`ult_lt_*`、`judge_cable`、`start_soc_*`）；**§1.7** `ambient_temp`→**`pid_chg`**；**§1.8** `dv2_ffc_ult_lt_*`→**ffc_level** 占位注释「**电池表生成**」；§1.3/§2/§3/§1.0 闸门口径已对齐。 |
| 2026-05-13 | 新增 **§1.1.2**（`ifod_threshold`、`rsw_min`、`ircmp_*`、`vta_cap_*`、`ita_cap_min`、`project_power`、`allow_not_check_ta_status`、`vbat_threshold`、`idvchg_pps_term`：参考老树、CP 相关须 Read 驱动）；**§1.1.3 `support_ta` 逐 token 转义**；§1.3/§2/§3/description 已交叉引用。 |
| 2026-05-13 | **§1.6**（初版）：**`tswchg_*`、`swchg_*`、`judge_vol_diff`、`idvchg_step`** 等勿写入 **`tc_pe5`**；**`ita_level_dual`/`rcable_level_dual`** 后续改为 **§1.0 单/双 CP 选源** + **§1.6 禁旧名落盘**。 |
| 2026-05-13 | 新增 **§1.0.1**：**`idvchg_level_multi`**（`ita_level[0]` + `ita_level_dual[0]`/7000 + 后两项同 L1）、**`run_cp_cur`**（0 / `idvchg_term×5` / `min(×7,4250)` / 同第三项）、**`run_cp_recovery_gap`** 与 **`run_wls_*`** 固定向量及「不支持无线则省略」；**description**、**§2**、**§3** 已交叉引用。 |
