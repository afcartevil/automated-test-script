---
name: mtk-adapt-upgrade-branch-orchestrator
description: 老分支升级新分支编排器：柱0信源与路径纪律→柱1器件→柱2参数（§5–§13/bridge/tran_battery/pe5-migrate）→柱3特性占位；柱3正文 handoff 至 transsion-sunmao40-customization-features-adapt。handoff 到 mtk-adapt-template-router 与 mtk-adapt-template-*。PE5 须 Read transsion-pe5-migrate-dual-cp-k612。
---

# MTK 老分支升级新分支：编排器

## 状态

**路径解析纪律 §1～§13**、**§3.2.1 闸门**、**与其它 skill 关系表** 已可执行。按 **三柱模型** 重组后的 **阶段占位（范围冻结、3B、验证矩阵等）** 仍为骨架，供你基于同一模型填补。

## 三柱升级模型（与新分支适配 skill 对齐）

新分支上「怎么适配」已由 **`mtk-adapt-template-router`** 按 **器件 → 基本充电能力参数 → 客制化特性** 三柱写清（`mtk-adapt-template-device-*`、`mtk-adapt-template-basic-charging-capability`、**`transsion-sunmao40-customization-features-adapt`**）。**老分支升级新分支**不另起第四套流程，而是：

| 柱 | 含义 | 本编排器 + 其它 skill 的职责 |
|----|------|--------------------------------|
| **柱 0** | **新老信源与对照** | 用户给出老侧 **`OLD_TRAN_ROOT`**（如 `tran_projects/.../lj9`）；新侧路径按 **下文「路径解析纪律」** + `mtk-adapt-upgrade-inventory-checklist` 列举老文件、拼 `project_full` / DWS / LK / charge overlay。**不**全树 `grep` 反推项目。 |
| **柱 1** | **器件适配** | 从老树 dtsi/include/`compatible`/I2C **归纳器件列表** → **`Read` `mtk-adapt-template-router`** → 各 **`mtk-adapt-template-device-*`**，与绿场 **同一套** SKILL 落盘。编排器 **不写** IC 寄存器级细节。**RFC / TA 硬件**：**先按 `mtk-adapt-template-device-charge-pump`**（与 `protocol_ta` / TFCP / DWS 联动）；不足由项目补充。**柱 1 还须核对 Preloader / LK2 顶层 `*.mk`**（见 **`mtk-adapt-upgrade-inventory-checklist` B.1.2**）：实际参与编译的 **preloader `custom/<project_full>/` 主 mk**、**`lk2/project/<project_full>.mk`** 与老分支 **overlay→主 mk 更名** 是否一致，且 **`TRAN_*` / `CUSTOM_*` / `tc_charger_lk.dtsi` include** 与 **器件清单、DWS** 无冲突。 |
| **柱 2** | **参数适配** | 从老树 **抽 dtsi 参数**，按 **路径纪律 §5～§13**、`transsion-charger-dtsi-driver-bridge`、`transsion-tran-battery-to-tc-charger-dtsi`、`transsion-pe5-migrate-dual-cp-k612` 等映射到新 KDM 节点，并汇入 **`mtk-adapt-template-basic-charging-capability`**。器件节点内专属数值随 **柱 1** 所选 device skill。 |
| **柱 3** | **特性适配** | **先占位**：柱 2 完成后经 **`mtk-adapt-template-router`**；**柱 3 输入**以 **用户口述** 为主（见 **`transsion-sunmao40-customization-features-adapt`** **RULE-0**），可选 **`pillar3-customization-input.md`**；**仅**处理口述中 **「要做」** 的条目并 **`Read` 合并 skill**；未声明「要做」的不改码（无工作量时 **「此项特性无适配工作量」**）；收尾 **提示未声明项**；口述与表均未给出「要做」则停柱 3 反问用户。 |

**执行顺序**：柱 0 → 柱 1 → 柱 2 → 柱 3。下文 **§路径解析纪律** 为 **柱 0 新侧** 子集；**§5～§13** 为 **柱 2** 节点级规则索引。

### 与原「阶段」编号对照（便于检索旧文）

| 原阶段 | 三柱归属 | 说明 |
|--------|----------|------|
| 阶段 2 Inventory | **柱 0** | 信源清单，见 `mtk-adapt-upgrade-inventory-checklist`。 |
| 阶段 3.1 | **柱 1** 输入 | 器件/总线摘要 → handoff 到 router device-*。 |
| 阶段 3.2 / 3.3 | **柱 2** | DTSI 语义与基本充电参数；§3.2.1～§3.2.2、与 `basic-charging-capability` 对齐处待补全。 |
| 阶段 3.4 | **柱 3** | 特性清单占位。 |
| 阶段 4 platform-delta | **辅助闸门** | `mtk-adapt-upgrade-platform-delta-table`，补充柱 2，不替代 bridge。 |
| **阶段 5** | **回到 router** | **必须**按 **器件 → 基本充电能力参数 → 客制化特性** 顺序落盘：**柱 1/2** `Read` **`mtk-adapt-template-device-*`** / **`mtk-adapt-template-basic-charging-capability`**；**柱 3** `Read` **`transsion-sunmao40-customization-features-adapt`**；`ProjectConfig.mk` 等随各柱落地，**器件柱完成后可选** 老新 `ProjectConfig.mk` diff 查游离行。 |
| 阶段 6 | **验证** | 与各模板验证清单合并，待补。 |

## 路径解析纪律（新分支 / 升级必守 · 柱 0 新侧）

执行者在 **新分支 AOSP 根目录** 下定位项目文件时，**必须**遵守下列顺序；**禁止**为反推项目位置而对整棵 AOSP / 整棵 `kernel-*` 做无边界 `grep` / 全量树扫描（易超时、易命中无关工程、且与 Tran 目录约定不一致）。

### 1) 先按器件 skill 拼路径，再打开验证

1. **输入**：用户给出 **项目短名**（如 `cl6k`）或 **直接给出 `project_full`**（如 `cl6k_h898`）。若仅短名：严格按 **`mtk-adapt-template-device-pd-ic` / `mtk-adapt-template-device-charge-pump`** 的 **§0.1 `project_full` 解析规则**：在 `vendor/transsion/projects` 下匹配 `<project_short>_*`；命中多个则 **停下问用户** 指定唯一目录名。  
2. **平台小写名**：`Read` `vendor/transsion/projects/<project_full>/ProjectConfig.mk`，解析 `MTK_PLATFORM` → `mtk_platform_lower`（规则见上述器件 skill §0.2）。  
   - 若该路径不存在：再尝试 **`vendor/vendor/transsion/projects/<project_full>/ProjectConfig.mk`**（部分树存在双层 `vendor/`；仅允许这一处「规则内回退」，仍失败则 **停下问用户**）。  
3. **Kernel DWS**：按 §0.3 拼接并尝试 `Read`：  
   `vendor/mediatek/proprietary/tools/dct/dws/<mtk_platform_lower>/<project_full>.dws`  
   （若不存在：**停下问用户** 提供实际 `kernel_dws_path` 或确认 `project_full`。）  
4. **Preloader `codegen.dws`**：按 `mtk-adapt-template-device-charger-ic` / `charge-pump` 中示例结构，将 `<project_full>` 代入 `preloader/custom/<project_full>/dct/dct/codegen.dws`（或你们文档规定的等价路径）；**仅**在已确认 `project_full` 后打开该文件；不存在则 **停下问用户**。**DWS 老→新目录映射、GPIO 溯源表与「先列表再对比」纪律** 见 `mtk-adapt-upgrade-inventory-checklist` **「DWS 映射模板与同步工作流」**。  
5. **LK `tc_charger_lk.dtsi` 等**：按 `mtk-adapt-template-device-charger-ic` 中 **`tc_charger_lk.dtsi` 路径规则**（6.12 / 6.6 / 6.1 模板 + `vendor/` 前缀回退）拼接 `<project_full>` 后 `Read`；不存在则 **停下问用户**。  
6. **Kernel 充电 overlay dtsi**（`mediatek/charge/<project_full>/` 等）：仅在上述步骤已成功定位 `project_full` 与内核树类型后，对 **已拼接出的目录** 做列举或单文件 `Read`；**不得**用关键字对整内核树盲搜以猜项目名。

### 2) 何时才允许使用 `grep`

- **仅**在「按 skill 已拼出的路径」或其 **直接父目录** 内做有限搜索（例如确认某 `compatible` 是否已出现在**已知**板级 dtsi 中）。  
- **禁止**：从 AOSP 根或 `kernel-6.12` 根起，用器件名 / `compatible` 对全树 `grep` 以推断 `project_full` 或板级路径。

### 3) 失败处理

任一必备文件在「规则内回退」后仍不存在：**停止自动化推断**，向用户说明已尝试的拼接路径清单，并请求补充：实际 `project_full`、双层 `vendor/` 与否、`kernel_device_modules` 相对根路径、或缺失文件的准确位置。

### 4) 硬件强相关、可与老分支直接对齐的修改（落盘后告知）

下列字段与 **BOM / 走线 / 器件手册中的静态连接** 强相关；在 **已能同时打开老分支与新分支对应 dtsi（及必要时 DWS）** 且用户未声明「硬件改版」的前提下，若新分支相对老分支出现 **明显笔误或与老树不一致**（例如 charge pump **从片 `rm_slave_addr`、I2C `reg`、IRQ GPIO 号** 等与老侧证据矛盾），**允许直接在新分支修改** 使与 **老分支器件描述一致**，**不必**再走「逐项等人确认后再改」的流程（与 **充电策略参数**、**5.10→新栈语义迁移**、**温区/电流表** 等需 `transsion-charger-dtsi-driver-bridge` 或用户分批确认的情形区分）。

**执行要求：**

- 修改前在会话中 **点名证据**：老侧文件路径 + 摘录，新侧修改前摘录。  
- 修改后 **简短告知用户**：已改文件路径、字段名、旧值→新值、对齐的老侧依据。  
- **不适用**本条、须停下确认的情况：用户声明 **换板/换料**；老新 **芯片型号不同**；仅能从「想要的行为」推断而不能从老树 **唯一确定** 的数值。

### 5) 明确不迁移：`tran_battery_aging`（`tran,chg_aging`）

老分支 DTS 若含 **`tran_battery_aging` / `compatible = "tran,chg_aging"`**（含 `battery_aging_module0..3` 等）：**新分支不写等价节点**，本编排流程 **直接忽略**——**不**生成迁移 dtsi 片段、**不**纳入 3B 待确认批、**不要求**用户做字段映射；Inventory 命中后标注 **「已识别，按策略跳过」** 即可。与 **`transsion-tran-battery-to-tc-charger-dtsi`** §0 一致。

### 6) `tran_otg`（`tran,otg_fun`）：**仅 老 → 新**（compatible + 模板补全 + `[REVIEW]`）

- **第一**：老树节点 **核对 `compatible` 必须为 `tran,otg_fun`**；异常则停、`[REVIEW]`（见 **`transsion-charger-dtsi-driver-bridge`**「`tran_otg` 迁移工作流」§1）。
- **第二**：**6.12 `tran_otg` 可配项多于 5.10 老树**；老树 **未出现** 的 6.12 属性，**一律**用 **bridge 上表默认 + `mtk-adapt-template-basic-charging-capability` 的 `tran_otg` 模板** 写入新 DTS；老树已有 **`otg_boost_curr_*`** 的须改名为 **`tc_otg_boost_curr_*`** 再写入新侧（见 bridge **§3**）。
- **第三**：**生成完成后**，凡 **模板补全**、**改名映射**、**PD 反向充电 / boost / 温控** 相关项 **全量标注 `[REVIEW]`**，便于 OTG/反向充电实机核对（见 bridge **§4**）。**本编排不涉及「新 → 老」OTG 落盘。**

### 7) `tran_auto_test` → `tc_auto_test`（**compatible + 节点名**）

老 DTS **`tran_auto_test` / `compatible = "tran,auto_test"`** 迁到新树时：**节点名** **`tc_auto_test`**，**compatible** **`"tc,auto_test"`**；全局替换 **`&tran_auto_test`** 等 phandle。证据见 **`transsion-charger-dtsi-driver-bridge`** 摘要表与 **「`tran_auto_test` → `tc_auto_test`」** 小节；合入后 **`[REVIEW]`** **`rg "tran,auto_test|tran_auto_test"`** 在板级应为零命中。

### 8) `water_detect`（`transsion, water_detect`）

- **compatible** 与 **独立节点** 在 6.12 **保留**；**`compatible` 字符串**（含 **逗号后空格**）须与 **`tc_water_detect.c`** 的 **`of_match`** 一致。
- **`scheme` 数值**：**0、1** 与老侧相同；**老 2→新 3**、**老 3→新 4**、**老 4→新 2**（见 **`transsion-charger-dtsi-driver-bridge`** **「`water_detect`」** 对照表）；纯 GPIO 示例 **`scheme = <1>`** **不改**。
- **`bootmode = <&chosen>`**：新 **`tc_water_detect`** **不解析**该属性，**可删**；bootmode 语义以 **`tc_get_boot_mode()`** 为准，**`[REVIEW]`**。
- 合入后若 **`scheme` 曾 ≥2**：**`[REVIEW]`** 进水检测实机。

### 9) `pid_chg`（`tran,pid_chg_algo` → `tc,pid_chg_algo`）

- **`compatible`**：**`tran,pid_chg_algo`** → **`tc,pid_chg_algo`**（与 **`transsion-charger-dtsi-driver-bridge`** **「`pid_chg`」** 一致）。
- **新树模板常多** **`ambient_temp`**、**`target_temp_array`**（各 **5** 元，与 **`power_level` 五档** 对齐）；老树无则 **从目标平台 `tc_charger.dtsi` 抄默认再调参**，**`[REVIEW]`**。
- **其余属性**：多数 **键名不变、数值可直拷**；合入后 **`rg "tran,pid_chg_algo"`** 预期零命中。

### 10) `ambient_detect` / `temp_forecast`（**`transsion,*` → `tc,*`**）

- **`ambient_detect`**：**`transsion,ambient_detect`** → **`tc,ambient_detect`**；**`qmax`～`power_delta_temp`** 多与老树 **整段直拷**（见 **`transsion-charger-dtsi-driver-bridge`** **「`ambient_detect` / `temp_forecast`」**）。
- **`temp_forecast`**：**`transsion,temp_forecast`** → **`tc,temp_forecast`**；**补 `pa_temp_gap`**（老树无则 **默认 `<500>`**，有量产基准则从基准）；**`machine_gap`** 是否保留以 **`tc_temp_forecast*.c`** 为准；**`orgin_rate` 勿被参考模板静默覆盖**（保留产品调参）。
- **`rg`**：**`transsion,ambient_detect`**、**`transsion,temp_forecast`** 板级预期零命中。

### 11) `support_alg` 子节点（**`&pe2` / `&tc30` / `&hvdcp20` / `&pdc`** → **`&tc_pe2` / `&tc_30` / `&tc_hvdcp20` / `&tc_pd`**）

- **fragment 目标名**见 **`transsion-charger-dtsi-driver-bridge`** **「`support_alg` 子节点」**（**`&tc30`→`&tc_30`** 下划线）。
- **属性**：**`*_ichg_level_threshold`→`ta_ichg_level_threshold`**；**`vbat_threshold` mV→µV**；**`sc_*`→`chr_volt*`**；**`pdc`：`sc_charger_current`→`charger_current_limit`**；**线缆阻抗 / 双串 DCS / ibus_err / vsys_watt`**：**`[REVIEW]`** 与 **`transsion-dcp-fastcharge-probe`**。

### 12) `extcon_usb`（**`&extcon_usb`**）

- **完全按新分支 SoC 基线 + 新 `tc_charger.dtsi` fragment**；**禁止**用老树 **`mediatek,extcon-usb` + `&switch_chg`** 整块覆盖。
- **6.12**：**Transsion extcon**（`compatible` 以芯片基准 dtsi + 驱动为准）；**其它内核**：常见 **`mediatek,extcon-usb`**。
- **`charger`**：**`&switch_chg`→`&tc_chgtype`**；**`remote-endpoint`**：**从芯片平台基准 dtsi 解析**（见 **`transsion-charger-dtsi-driver-bridge`** **「`extcon_usb`」**）。

### 13) `&pe5`：`mtk_pe50.dtsi`（**`mediatek,charger,pe5`**）→ **`tc_pe5`**（**6.12 `transsion/tc_pe5.c`**）

- **compatible**：老树 **`mediatek,charger,pe5`** → 新树 **`tc_pe5`**（以目标 **`tc_pe5.c` `of_match` / 板级片段** 为准）；**`charger`/`gauge` 老引用**须按新树 **`tc_chgtype` / gauge 节点**改写（与 **`transsion-charger-dtsi-driver-bridge`**、`support_alg` 编排一致处核对）。
- **热限流 `*_curlmt`（`tta` / `tdvchg` / `tbat` / `tpcb` / `tmachine` / multi `tbat_curlmt_*` 等）**：老 **`mtk_pe5.c`** 在 **dual/third DVCHG** 路径上对扣减使用 **`ita_lmt - (2 * curlmt)`**；新 **`tc_pe5.c`** **无**该分支，**恒为 `ita_lmt - curlmt`**。**禁止**把老树数值不经语义核对直接拷入新树。
- **迁移权威**：执行者在写出或审查 **`tc_pe5.dtsi`** 片段前 **必须 `Read` `transsion-pe5-migrate-dual-cp-k612`**：何时对 SOURCE 表做 **×2 对齐**、哪些项 **永不 ×2**（`sys_power_*`、`tswchg_*`、`ita_level_dual`、FFC、`conversion_ratio` 等）、**×3 在老栈 stock 路径不成立** 等。
- **Inventory / 简报**：命中老树 **`&pe5`** 或 **`mtk_pe50.dtsi`** 时，handoff 须含一行：**「PE5：`transsion-pe5-migrate-dual-cp-k612` 已读 / 热限是否 ×2 对齐结论」**。
- **`support_alg` 与 `&pe5`**：子节点改名（如 **`&pe2`→`&tc_pe2`**）见 **§11**；PE5 **数值语义**仍以本节与 **`transsion-pe5-migrate-dual-cp-k612`** 为准。

---

## 与其它 skill 的关系

| 角色 | Skill 名 | 三柱 / 用法 |
|------|-----------|-------------|
| 信源扫描清单 | `mtk-adapt-upgrade-inventory-checklist` | **柱 0**；若含 **`tran_battery`→`&charger`**，须 **Read** `transsion-tran-battery-to-tc-charger-dtsi`；若含 **`&pe5` / `mtk_pe50.dtsi`**，须 **Read** `transsion-pe5-migrate-dual-cp-k612`（见 **§13**） |
| 平台差分闸门 | `mtk-adapt-upgrade-platform-delta-table` | **辅助**（柱 2 前后闸门） |
| **`tran_battery`→6.12 `&charger`** | **`transsion-tran-battery-to-tc-charger-dtsi`** | **柱 2**：产出 `tc_charger` 片段前 **必须 Read** 全文 |
| **`mtk_pe50`→`tc_pe5`** | **`transsion-pe5-migrate-dual-cp-k612`** | **柱 2**：热限 `*_curlmt` ×2 语义；与 bridge 并存 |
| DTSI↔驱动语义 | `transsion-charger-dtsi-driver-bridge` | **柱 2**：按需 Read；`tran_battery` 数值以专用 skill 为准 |
| 新分支落地分流 | `mtk-adapt-template-router` | **柱 1～3** 入口；编排器 **阶段 5** 回到此处 |
| 器件 / 参数 / 特性落地 | `mtk-adapt-template-device-*` 等 | 经 router **按柱** 执行 |

---

## 前置输入契约（最小集 · 可继续扩充）

- **新分支**：AOSP 根路径；**新** `project_full` 或项目短名（解析规则见路径纪律 §1）。  
- **老分支**：用户给出 **`OLD_TRAN_ROOT`**（例如 `tran_projects/<系列>/<工程目录>/<vendor 同级>`），其下含 dtsi、LK mk、preloader mk、DWS 等。  
- **可选**：旧/新 KDM 版本、是否声明换板换料、升级范围（kernel / lk / pl / dws）勾选。

---

## 阶段 1 — 范围冻结

**三柱**：全局前置。**骨架占位**：子域勾选、版本字符串、冻结日期等（待补）。

---

## 阶段 2 — 信源清单 Inventory

**三柱：柱 0。** 调用 **`mtk-adapt-upgrade-inventory-checklist`**；输出「路径 + 一句角色」列表（模板见该 skill **块 F**，待补）。

---

## 阶段 3 — 语义抽取与 Normalize

**三柱：柱 1（§3.1）+ 柱 2（§3.2～3.3）+ 柱 3 输入（§3.4 占位）。**

### 3.1 器件与总线/IRQ/供电摘要

**柱 1 必含（与 `mtk-adapt-template-router` 二级分流一致）**

1. **Kernel / KDM dtsi**：`compatible`、`reg`、IRQ GPIO、主从 CP、`tc_pd`/`protocol_ta` 等（归纳表见 **`mtk-adapt-upgrade-inventory-checklist` A.2**）。  
2. **Preloader mk**：在 **`preloader/custom/<project_full>/`** 打开**实际参与编译**的顶层 **`.mk`**（老侧常为 `*_overlay.mk`、新侧可能为主 **`*.mk`**，对照 **`mtk-adapt-upgrade-inventory-checklist` B.1.1** 表头）；核对 **充电 / gauge / CP / PD** 相关宏与 **`ProjectConfig.mk`**、**`codegen.dws`** 一致。  
3. **LK2 mk**：在 **`vendor/mediatek/proprietary/bootable/bootloader/lk2/project/`** 打开 **`<project_full>.mk`**；核对 **`tc_charger_lk.dtsi`** 路径 include、**`TRAN_*`** 与 **`mtk-adapt-template-basic-charging-capability`**「**`tc_charger_lk.dtsi` 强约束**」是否满足。  

（预留：与 `mtk-adapt-template-router`「最小输入契约」字段对齐的展开表头。）

### 3.2 内核 DTSI 证据压缩

#### 3.2.1 老 KDM / kernel 5.10 闸门

- **含 `tran_battery` / `tran,chg_fun`（或同文件需迁的 `jeita_*_chg_cur`、`pcb_*`）**：执行者 **必须先 `Read` `transsion-tran-battery-to-tc-charger-dtsi`**，再写 **`&charger` 合并片段** 或 3B 批结论；**不**依赖用户单独 @ 该 skill。  
- **老侧仅存在 `tran_battery_aging`（`tran,chg_aging`）**：按 **`transsion-tran-battery-to-tc-charger-dtsi` §0** 与 **路径纪律 §5**，**直接忽略**，**不**为 aging 走 bridge 四步、**不**出迁移片段。  
- **更广的 DTSI↔驱动语义**（OTG、非 tran_battery 节点等）：按需 **`Read` `transsion-charger-dtsi-driver-bridge`** 并按其四步；与 tran_battery **并行**，bridge **不替代**上条专用 skill 的转换规则。**`tran_otg` 仅老→新**（编排器 **§6**）、**`tran_auto_test`→`tc_auto_test`**（**§7**）、**`water_detect` 的 `scheme`/`bootmode`**（**§8**）、**`pid_chg` 的 compatible 与 `ambient_temp`/`target_temp_array`**（**§9**）、**`ambient_detect`/`temp_forecast` 的 `transsion,*`→`tc,*` 与 `pa_temp_gap`/`machine_gap`**（**§10**）、**`support_alg` 子节点 `&pe2`…→`&tc_pe2`… 与 `chr_volt*`**（**§11**）、**`extcon_usb`（6.12 Tran extcon、`charger`、`remote-endpoint`）**（**§12**）以 bridge 正文为准。
- **`&pe5` / `mtk_pe50`→`tc_pe5`**：**必须** **`Read` `transsion-pe5-migrate-dual-cp-k612`**（编排器 **§13**）；bridge **不**替代 PE5 热限 **`curlmt` ×2 语义**与 **`conversion_ratio`** 分工。

#### 3.2.2 非 5.10 或其它大版本

（预留：何时仍建议走 bridge 的可选策略。）

### 3.3 基本充电能力参数表

（预留：与 `mtk-adapt-template-basic-charging-capability`「参数变更目标列表」对齐的列定义。）

### 3.4 客制化特性清单

（预留：与 **`transsion-sunmao40-customization-features-adapt`**（RULE-1/2/3/4）的 handoff 字段。）

---

## 阶段 3B — 与用户「分批逐一确认」协议（占位）

### 3B.1 分批单位

（预留：按老 DTS 节点 / 按 JEITA·PCB·aging·OTG 等区块——待与你定稿。）

### 3B.2 每一批固定输出结构

（预留：证据摘录 → 老侧语义 → 新侧落点 → 建议值与 `[REVIEW]` → 待确认问题。）

### 3B.3 状态机

（预留：`待确认` / `已批准` / `已修改` / `推迟`；**未批准**不得并入「可执行简报」或对新树做落地编辑。）

### 3B.4 留痕约定

（预留：`/* SOURCE: OLD-... */`、`/* CONVERT: ... */` 与 migrate 类 skill 图例对齐说明。）

---

## 阶段 4 — 平台差分闸门

**辅助柱 2。** 引用 `mtk-adapt-upgrade-platform-delta-table`（待补输出模板）。

---

## 阶段 5 — 回到 `mtk-adapt-template-router`（柱 1 → 2 → 3）

**必须**按 **器件适配 → 基本充电能力参数适配 → 客制化特性适配** 顺序，对已归纳的器件与参数 **`Read` 对应 `mtk-adapt-template-*`**，与绿场共用同一套 SKILL。**骨架占位**：子任务表「任务 | 下一 skill | 仍缺的人类输入」（待补）。

---

## 阶段 6 — 验证矩阵

**三柱之后收口。** 与各模板验证清单去重合并（待补）。

---

## 产物：适配简报（文件级占位）

### 简报章节标题约定

（预留：一级/二级标题列表，便于 PR 拆分。）

### 可选机器可读摘要

（预留：JSON 字段名草案，若不需要可删本节。）

---

## 边界

（预留：不替代根因分析类 skill；不重复 bridge 内长对照表；等。）

---

## 修订记录

| 日期 | 摘要 |
|------|------|
| 2026-05-12 | 新增 **§路径解析纪律**：新分支下优先按 `mtk-adapt-template-device-pd-ic` / `charge-pump` 拼 `project_full` 与 DWS/LK dtsi 路径；失败则停问用户；禁止全树 `grep` 反推项目路径。 |
| 2026-05-12 | 路径纪律 §1 第 4 步：补充指向 `mtk-adapt-upgrade-inventory-checklist` 中 **DWS 映射模板与同步工作流**。 |
| 2026-05-12 | 路径纪律新增 **§4**：硬件强相关且可与老分支唯一对齐时（如 CP 从片地址笔误），可直接改新树并落盘后告知用户；排除换板换料与策略参数。 |
| 2026-05-12 | **与其它 skill 关系表**：新增 **`transsion-tran-battery-to-tc-charger-dtsi`** 为阶段 3/3B **强制 Read**（`tran_battery`→`&charger`）；**`transsion-charger-dtsi-driver-bridge`** 改为与前者并存、按需 Read。§3.2.1 同步上述闸门表述。 |
| 2026-05-12 | 路径纪律下新增 **§5**：老侧 **`tran_battery_aging`（`tran,chg_aging`）** 新树 **忽略不迁**；与 `transsion-tran-battery-to-tc-charger-dtsi` §0 对齐。 |
| 2026-05-12 | 路径纪律新增 **§6**：**`tran_otg`** **仅老→新**；compatible；模板补全；**`otg_boost_*`→`tc_otg_boost_*`**；**`[REVIEW]`**；见 **`transsion-charger-dtsi-driver-bridge`**。 |
| 2026-05-12 | 路径纪律新增 **§7**：**`tran_auto_test`→`tc_auto_test`**（**`tran,auto_test`→`tc,auto_test`**、phandle）；见 **`transsion-charger-dtsi-driver-bridge`**。 |
| 2026-05-12 | 路径纪律新增 **§8**：**`water_detect`**（**`transsion, water_detect`**）：**`scheme` 数值重映射**、**`bootmode` DT 弃用**；见 **`transsion-charger-dtsi-driver-bridge`**「`water_detect`」；§3.2.1 并入 **§8** 指针。 |
| 2026-05-12 | 路径纪律新增 **§9**：**`pid_chg`**（**`tran,pid_chg_algo`→`tc,pid_chg_algo`**）；**`ambient_temp` / `target_temp_array`**；见 **`transsion-charger-dtsi-driver-bridge`**「`pid_chg`」；§3.2.1 并入 **§9** 指针。 |
| 2026-05-12 | 路径纪律新增 **§10**：**`ambient_detect`/`temp_forecast`**（**`transsion,*`→`tc,*`**）；**`pa_temp_gap`/`machine_gap`/`orgin_rate`**；见 **`transsion-charger-dtsi-driver-bridge`** 同题小节；§3.2.1 并入 **§10** 指针。 |
| 2026-05-12 | 路径纪律新增 **§11**：**`support_alg` 子节点**（**`&pe2`…→`&tc_pe2`…**、**`chr_volt*`**、**`vbat_threshold` µV**）；见 **`transsion-charger-dtsi-driver-bridge`**「`support_alg` 子节点」与 **`transsion-dcp-fastcharge-probe`**；§3.2.1 并入 **§11** 指针。 |
| 2026-05-12 | 路径纪律新增 **§12**：**`extcon_usb`**（**新分支为准**、**6.12 Tran extcon vs mediatek**、**`charger`→`tc_chgtype`**、**`remote-endpoint` 跟 SoC 基准 dtsi**）；见 **`transsion-charger-dtsi-driver-bridge`**「`extcon_usb`」；§3.2.1 并入 **§12** 指针。 |
| 2026-05-12 | 柱 1 表：RFC/TA **先 `mtk-adapt-template-device-charge-pump`**（用户定稿）。 |
| 2026-05-13 | **§10 `temp_forecast` / `pa_temp_gap`**：老树无则 **默认 `<500>`**（有量产基准则从基准），与 **basic-charging-capability** / **bridge** 一致。 |
| 2026-05-13 | **柱 1**：三柱表与 **§3.1** 增补 **Preloader / LK2 `*.mk` 必选核对**；与 **`mtk-adapt-upgrade-inventory-checklist` B.1.2** 对齐。 |
