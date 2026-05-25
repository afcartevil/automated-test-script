---
name: tran-projects-config-migrate-dtsi-dws
description: 将 tran_projects 老路径配置迁移到新 vendor 路径，覆盖 DTSI include、DWS（kernel/preloader）、Preloader `<BOARD>.mk`、LK2 `project/<BOARD>.mk`（gauge/KPOC 等 Tran 宏）、Tran `ProjectConfig.mk`（关机充电 logo/KPOC）、GPIO 与 KO 核对。用户提到 tran_projects 老分支、路径重映射、dtsi/dws/bootloader/迁移或新老对齐时使用。
disable-model-invocation: true
---

# Tran Projects 配置迁移（DTSI + DWS + Bootloader 要点）

## 适用范围

满足以下场景时使用本 skill：
- 从 `tran_projects/...` 老分支迁移到新源码树；
- 需要先按内核版本分流（`kernel-5.10` 与其它内核）再执行迁移；
- 需要保持 DTSI 参数与特性开关一致；
- 需要同步 DWS（`tools/dct` 与 preloader `codegen.dws`）；
- 需要核对充电/电源相关 GPIO 一致性；
- 需要核对 **Preloader**、**LK2 主工程 `project/<BOARD>.mk`**、以及 **Tran `ProjectConfig.mk`** 中与充电栈 / gauge / 关机充电动画相关的 **makefile 宏**（与 DTS 器件一致，避免只改内核漏改 bootloader/ODM）。

本 skill 针对 Transsion + MediaTek 工作流优化。

## 必做流程

1. 先确认 board/chip、内核版本与新老根目录。
2. **先做内核分流**：
   - `kernel-5.10`：仅 DTSI 迁移策略按“框架差异”执行（见下文「DTSI 分流规则」）。
   - 其它内核（如 `6.1/6.6/6.12`）：按常规路径映射 + 参数对齐执行。
3. 修改前先建立明确的 old->new 路径映射表。
4. 先迁移 DTSI，再迁移 DWS。
5. 再核对 **Preloader `<BOARD>.mk`**（充电泵等）与 **LK2 `project/<BOARD>.mk`**（gauge 类 Tran 宏、`TRAN_CHARGER_KPOC_ANIMATION` 等）：**老新各读一遍并 diff**，禁止在未确认构建脚本的前提下 **新建** `*_overlay.mk`。
6. 再核对 **Tran `projects/<BOARD>/ProjectConfig.mk`** 中与关机充电相关的 **`TRAN_CHARGER_KPOC_ANIMATION`、`CUSTOM_TRAN_LOGO`**（与 LK2 侧 KPOC 宏对照）；**仅改 `CUSTOM_TRAN_LOGO` 时不要顺带改 `TRAN_PRODUCT_*`**（见 **`transsion-sunmao40-customization-features-adapt`** **RULE-2**）。
7. 通过读取新老文件校验 GPIO（不要假设 copy 一定成功）。
8. 输出 `same / changed / missing / risky` 结论。

## DTSI 分流规则（kernel-5.10 vs 其它内核）

### A) `kernel-5.10`

- `kernel-5.10` 同步到新内核时，**DTSI 框架可能已重构**（目录、节点拆分、属性命名、include 关系都可能变化）。
- 执行策略：
  1. 先做“语义对齐”而非“逐文件 copy”；
  2. 按功能块迁移（charger / pe5 / gauge / usb / wireless 等），逐块映射到新框架落点；
  3. 老树字段若在新框架无等价项，标记 `missing-by-design` 并给出替代建议；
  4. 保留老项目目标行为，不强行保留老文件结构。
- **边界明确**：`kernel-5.10` 的特殊处理仅限 **DTSI**；`DWS`、Preloader/LK2、`ProjectConfig.mk` 仍按本 skill 通用规则执行。

### B) 其它内核（`6.1/6.6/6.12` 等）

- 默认按 old->new 路径映射进行 DTSI 迁移；
- 以“参数与行为对齐”为主，文件组织差异较小时可采用同名文件对齐；
- 若出现局部框架差异，按 `kernel-5.10` 的“语义对齐”子策略处理该局部。

## old->new 路径映射模板

占位符说明：
- `<OLD_ROOT>` = 老 `tran_projects` 工程根目录
- `<NEW_ROOT>` = 新工程根目录
- `<BOARD>` = 板级名，例如 `lj9_h972`
- `<CHIP>` = 芯片名，例如 `mt6897`

### DTSI 映射

- 老路径基准：
  - `<OLD_ROOT>/kernel/kernel_device_modules-<KDM_VER>/arch/arm64/boot/dts/mediatek/`
- 新路径基准（推荐 board 子目录化）：
  - `<NEW_ROOT>/vendor/kernel/kernel_device_modules-<KDM_VER>/arch/arm64/boot/dts/mediatek/<board-folder>/`

其中 `<KDM_VER>` 不固定，需按工程实际识别（常见如 `6.1`、`6.12`）。

常见迁移策略：
- 老树扁平 dtsi（如 `tc_charger.dtsi`）迁到新树 board 文件夹（如 `mediatek/lj9/tc_charger.dtsi`）
- 同步更新 board dts 的 include，从老路径改为新 board-folder 路径
- 除非用户明确要求平台化升级，否则参数值优先保持老板一致

### `tc_charger.dtsi` 周边：`mt6375_chg` 与 `&extcon_usb` graph

以下两条在迁移或手写生成 `tc_charger.dtsi` / charge overlay 时 **必须执行**，并写入迁移说明（含芯片名与 dts 路径证据）。

**适用范围（内核版本）**：第 **1** 条（`&mt6375_chg`）在 **`kernel_device_modules-6.1` / `6.6` / `6.12` 等** 新 KDM 树中均需按硬件核对；第 **2** 条（`&extcon_usb` 的 **`port` / `remote-endpoint` 与芯片基 dts 对齐**）**当前仅按 `kernel_device_modules-6.12` 上 `tc_charger` / `transsion,extcon-usb` 与 SoC `extcon_usb`↔`usb` graph 接法固化**——**`6.1`、`6.6` 等若 extcon 无 graph、对端 label 不同或与 USB 绑定方式不同，不得套用本条默认结论**，须在该 `KDM_VER` 的 `<chip>.dts` 与板级 overlay 中 **单独 grep 建立证据**后再写。

1. **`&mt6375_chg` 是否禁用**（新 KDM 通用）  
   - 若项目 **未使用 MT6375 作 charger PMIC**（充电主链走 `tc_chgtype` / 外挂 charger 等），新树 charge 片段中通常应保留：  
     `&mt6375_chg { status = "disabled"; };`  
   - 依据：硬件 BOM + 原理图 + 现网参考机 dtsi；**不要**在未核对的情况下打开 `mt6375_chg` 以免与真实充电路径冲突。

2. **`&extcon_usb` 下 `port` / `remote-endpoint` 必须与芯片基 dts 一致**（**仅 6.12**：见上「适用范围」）  
   - 旧 `kernel-5.10` 的 `&extcon_usb` 往往 **无** `port { endpoint … remote-endpoint }`；在 **`kernel_device_modules-6.12`** 上，新 `transsion,extcon-usb` / `mediatek,extcon-usb` 常与 **USB2 DRD graph** 绑定。  
   - **必须**在芯片基 dts 中核对原生写法，路径形态：  
     `<NEW_ROOT>/vendor/kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/<chip>.dts`  
     （例如 **MT6789** 上 `extcon_usb` 的 `usb_role: endpoint@0` 与 `usb` 节点内 `musb_drd_switch: endpoint@0` 成对，原生为 `remote-endpoint = <&musb_drd_switch>;`）。  
   - **禁止**从旧分支凭记忆写 `remote-endpoint`：换芯片后对端 label 可能不同；应以 **当前 `<chip>.dts` 内 `extcon_usb` 与 `usb` 节点的 graph 定义** 为准，并在输出中注明 grep/行号。

### `&u2port0`：USB2 眼图参数（`mediatek,eye-*` / `discth` / `rev6` 等）

以下属性属于 **USB2 端口眼图与电气调参**（device / host 两套常见后缀 `-host`），与 charger PMIC、`tc_charger.dtsi` 无直接耦合；迁移时仍须单独成块说明，避免误归入「充电参数」。

```dts
&u2port0 {
	mediatek,eye-vrt = <7>;
	mediatek,eye-term = <1>;
	mediatek,rev6 = <2>;
	mediatek,discth = <12>;
	mediatek,eye-vrt-host = <7>;
	mediatek,eye-term-host = <0>;
	mediatek,rev6-host = <2>;
};
```

**标注与核对纪律**

1. 在迁移输出、生成 fragment 或注释中，将该节点（或该属性组）**显式标为「眼图参数」**，与 OVP、BC1.2、`tc_misc` 等充电项分列。
2. **对照老 dtsi**：在 **用户指定的老树范围**（常见：`tran_projects` 下板级 dts、与充电同批 include 的 dtsi；**不要**只搜 `tc_charger.dtsi` 文件名）内 **grep** `u2port0`、`mediatek,eye-vrt`、`mediatek,eye-term` 等。
3. **若老树中找不到等价节点或等价属性**（常见：旧树未展开 `&u2port0` 或仅有平台默认、无显式 eye 字段）：新树补上的数值一律视为 **非继承自老板**，必须标 **`[REVIEW]`**（或等价注释，例如：`/* 眼图参数 | SOURCE: NEW-framework 占位（旧树未含；[REVIEW]） */`），由硬件 / USB / SI 按新平台参考机或实测确认后再收口，禁止静默当成「已与老机一致」。

### OLD `tran_battery`（`compatible = "tran,chg_fun"`）→ 新 KDM `&charger`（`compatible = "tc,charger"`）

旧 `kernel-5.10` 中 `drivers/power/supply/tran_chg/tran_charger.c` 以 **`tran,chg_fun`** 绑定 **`tran_battery`**，DTS 属性读入全局 `chg` 后供 **`set_jeita_charging_current` / `change_current_by_pcb_temp`** 等使用。新 **`kernel_device_modules-6.12`** 上 **`tran,chg_fun` 不再承接**；策略落在 **`transsion/tc_charger.c`** 的 **`tc_desc`**、**`single_batt_level_*`** 与 **`tc_basic_charger.c`**。删除旧 **`tran_battery`** 节点时：**`jeita_*`、`pcb_*`、`bootmode` 等属性名**随节点删除；**数值**按下面表格与子节迁移到 **`&charger`**。

**`tran_battery_aging`（`compatible = "tran,chg_aging"`）**：原驱动为 **`tran_battery_aging.c`**（FG/循环老化表、sysfs）。**新 KDM `transsion` 无此 compatible**；老化与健康度由 **gauge 守护、`tc_gauge`/health、`tc_charger` 的 `aging_*_uisoc` 等**处理。**老 → 新补充 DTS 时可直接删除该整段节点**，**不要**在 `tc_charger.dtsi` 中做一对一名义迁移。细则见 **`transsion-charger-dtsi-driver-bridge`** 对照表。

**新栈无 `enable_pcb_tml` 布尔**：旧树「关 PCB 限流」= 不写/不使能一段逻辑；新树 **无同名开关**，**是否做 PCB 热减额**取决于 **`tpcb_ichg[]` 是否全 0**（全 0 等价于不在 `tpcb` 档拉低电流）以及是否进入 **`tc_check_tpcb_level`** 路径。**老→新仍要换算**：若产品要延续旧 PCB 折线行为，必须把旧 **`pcb_temp_*` / `pcb_cur_*`** **拟合**进 **`tpcb_temp` + `tpcb_ichg`**（见下「`tpcb_*` 转换」）。

迁移时遵守以下规则（与 `docs/tc_charger.dtsi` 中 **MIGRATE-6.12**、**CONVERT-OLD-JEITA**、**CONVERT-TBAT-TPCB** 注释一致；**`jeita_*_input_cur`** 可按项目省略）。

| 旧 `&odm` / `tran_battery` | 新 `&charger` 落地 | 说明 |
|------------------------------|----------------------|------|
| `jeita_*_chg_cur`（µA） | **`single_batt_level` + `single_batt_level_0..N-1`** | 电池温区 **CC** 迁入 **`struct batt_desc`**；匹配 **`tbat > temp_lo && tbat <= temp_hi`**（`tc_get_battery_temperature()`，℃）。**左边界严格大于**：如 below T0 档常用 **`temp_lo = -11`** 以覆盖 **-10℃**。六档分界：**[REVIEW]** 与电芯/M TK 一致。 |
| `jeita_*_input_cur` | 通常 **不落** 同名温区表 | 新栈 ICL 以 `dcp_input_current`、`max_input_current_limit`、协议栈为主；项目可显式写「省略」于迁移说明。 |
| `enable_pcb_tml` | **（无同名）** | 不由 DTS 布尔控制；见 **`tpcb_ichg`** 与下节 **`tpcb_*` 转换**。 |
| `pcb_temp_step_one`、`pcb_temp_step_two` | **`tpcb_temp[]` 中的关键分界（℃）** | 旧值为 **毫摄氏度**：**除以 1000** 得到 **`tpcb_temp` 使用的整数 ℃**（与 `tc_get_tpcb_temp()` 一致）。 |
| `pcb_cur_step_one`、`pcb_cur_step_two` | **`tpcb_ichg[]`（拟合）** | 旧算法为两段**一次函数**累加 `delta_current` 再从目标电流扣除；新算法为按 PCB **档位**减 **`tpcb_ichg[level]`**（µA）。**不能**逐字段复制，须在 **`pcb_temp_*` 换算后的阈值**上按旧公式取样，反推各档 **`tpcb_ichg`**，使高温段等效电流接近（**[REVIEW]** 实机）。 |
| `pcb_min_chg_cur` | **`min_charger_current`** | 单位 µA 一致。 |
| `bootmode`（仅在 `tran_battery`） | **`tc_misc` 等已有 `phandle bootmode`** | 删除空壳 **`tran,chg_fun`**；bootmode 不丢。 |
| **`tran_battery_aging`（`tran,chg_aging`）** | **（不写）— 整段删除** | 新栈无同名驱动；迁移时 **直接删节点**，见上文专段。 |

#### `tpcb_temp` / `tpcb_ichg`：旧 `pcb_*` → 新表（算法差异与换算步骤）

1. **单位**：`pcb_temp_step_*`（m°C）→ **`T_c = 值 / 1000`**（℃），填入或对齐 **`tpcb_temp[]`** 中与旧 **`step_one` / `step_two`** 对应的档位边界（数组长度须与 `tc_charger` **`TC_LEVEL_MAX`** 一致，常与 **`tpcb_ichg`** 同维）。**`tpcb_temp_gap`** 对应新栈回滞，旧树无同名项时常保留默认 **1** 或按参考机。
2. **旧 `change_current_by_pcb_temp()`（有线路径）**：在 `Tpcb ≤ pcb_temp_step_one` 时 `delta_current=0`；在 **`(step_one, step_two]`** 内 **`delta = (T - step_one) * pcb_cur_step_one`**（注意旧 **`thermal_get_ap_ntc_temp()`** 与 **`tpcb` 的温度单位均为与内核热接口一致的量，通常 m°C 参与乘法，与 `pcb_cur_step_*` 标定一致）；**`T > step_two`** 时为两段折线。**新栈**：有效充电电流一侧为 **`min(..., max_charging_current_limit - tpcb_ichg[level])`**（再与 **`single_batt`/`vbat_cc`** 等合成，见 `tc_basic_charger.c`）。  
3. **拟合建议**：在 **`T = step_one`、`T = step_two`、`T = step_two+Δ`** 等取样点，用旧公式算 **目标 CC 扣减量**（或相对 **`max_charging_current_limit`** 的应减 **µA**），把扣减量映射到最接近的 **`tpcb_ichg[i]`** 阶梯；高温档可抬高对应 **`tpcb_ichg`**。若项目决定 **不做 PCB 限流**：**`tpcb_ichg` 全 0**（等价于旧 **`enable_pcb_tml` 关** 的「不扣 PCB」效果），但仍建议保留 **`tpcb_temp`** 占位与迁移记录。
4. **无线**：若旧 `tran_battery` 含 **`wireless_pcb_*`**，用同一拟合思路写入 **`tpcb_*`/`tpa_*`/无线专用逻辑**（以当前工程 **`tc_charger`/wireless** 区实际解析属性为准，**[REVIEW]**）。

#### `tbat_temp` / `tbat_ichg`：与 `single_batt` 分工及迁移

- **旧 `jeita_*_chg_cur` 已迁到 `single_batt_level_*`** 时：**主 JEITA CC** 由 **`vbat_cc`（`single_batt`）** 表达。  
- **`tbat_temp`/`tbat_ichg`** 在新栈表示 **另一套「电池温档位 → 从 max 减额」**（与 **`tc_check_tbat_level`** / `tc_basic_charger` 合成有关），**与 `single_batt` 可能叠乘/取 min**，迁移时须避免与 **`single_batt` 重复同一物理温区的双重扣减：  
  - **做法 A**：主电流曲线只放在 **`single_batt`**，则 **`tbat_ichg` 常置 0** 或仅保留弱减额，并由项目确认。  
  - **做法 B**：若旧机除 JEITA 表外还有**独立**「电池温 × 再限流」策略，再把其量化进 **`tbat_temp`/`tbat_ichg`**，并与 **`single_batt`** 分段**分工**写进迁移说明。  
- **缺省**：树内 **`tbat_temp`/`tbat_ichg`** 可与 **`tc_charger` default_info** 或参考机对齐，标 **[REVIEW]**；**旧 `tran_battery` 无同名数组**，无自动逐字翻译。

**`&charger` 必查**：**`support_alg`**（如 `"pe5"`, `"tc30"`, `"pd"`, `"hvdcp20"`, `"pe20"`）**禁止漏删**。

**`single_batt_level_M` 数组布局**（`struct batt_desc`）：`temp`×2、`ffc_status`、`vbat`×6、`ibat`×6、`eoc`、`cycle_cnt`×2、`rechg_gap`；`ffc_status=-1`；`cycle_cnt` 双 **-1** 表示不按循环筛档（**[REVIEW]** 解析版本）。

### DWS 映射

Kernel 阶段 DWS：
- old: `<OLD_ROOT>/vendor/mediatek/proprietary/tools/dct/dws/<CHIP>/<BOARD>.dws`
- new: `<NEW_ROOT>/vendor/vendor/mediatek/proprietary/tools/dct/dws/<CHIP>/<BOARD>.dws`

Preloader 阶段 DWS：
- old: `<OLD_ROOT>/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<BOARD>/dct/dct/codegen.dws`
- new: `<NEW_ROOT>/vendor/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<BOARD>/dct/dct/codegen.dws`

注意：
- 有的树是 `vendor/mediatek/...`（单 vendor），有的是 `vendor/vendor/mediatek/...`（双 vendor）。
- 拷贝前必须先检查真实文件系统路径是否存在。

### Preloader / LK（bootloader）路径与编辑纪律

**路径映射（占位符与上文一致）**

- Preloader 板级 makefile（常见主入口）：
  - old: `<OLD_ROOT>/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<BOARD>/<BOARD>.mk`
  - new: `<NEW_ROOT>/vendor/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/<BOARD>/<BOARD>.mk`  
  （若工程为单 `vendor/`，则去掉一层 `vendor/`。）

- 老树可能出现的 overlay（仅当老树构建 **明确 include** 时才对等迁移）：
  - `<BOARD>_overlay.mk`，路径与同目录 `custom/<BOARD>/` 或文档约定一致。

- LK2 板级 overlay（同样 **必须先确认新树是否引用**）：
  - old/new: `.../bootable/bootloader/lk2/project/<BOARD>_overlay.mk`

- **LK2 主工程 makefile（多数项目的实际落点，必查）**  
  - old: `<OLD_ROOT>/vendor/mediatek/proprietary/bootable/bootloader/lk2/project/<BOARD>.mk`  
  - new: `<NEW_ROOT>/vendor/vendor/mediatek/proprietary/bootable/bootloader/lk2/project/<BOARD>.mk`  
  - 说明：Tran 的 gauge/KPOC/haptic 等 **宏常写在本文件**，不要只盯着 `*_overlay.mk` 而漏掉 `<BOARD>.mk`。

- **Tran 工程 `ProjectConfig.mk`（关机充电动画 / LOGO 宏，必查）**  
  - old: `<OLD_ROOT>/vendor/transsion/projects/<BOARD>/ProjectConfig.mk`（若老树目录层级不同，以实际包含 `TRAN_CHARGER_KPOC_ANIMATION` 的文件为准）  
  - new: `<NEW_ROOT>/vendor/vendor/transsion/projects/<BOARD>/ProjectConfig.mk`  
  - 必 grep：`TRAN_CHARGER_KPOC_ANIMATION`、`CUSTOM_TRAN_LOGO`

### 为何容易遗漏（LK gauge 宏与关机充电宏）

此前迁移 checklist **偏重 DTSI + DWS + Preloader**，容易出现：

1. **LK2 主文件未纳入 diff 范围**：文档若只提 `lk2/project/<BOARD>_overlay.mk`，而工程实际使用 **`lk2/project/<BOARD>.mk`**，则 **`TRAN_SINGLE_GAUGE` / `TRAN_DUAL_BATTERY` / `TRAN_LOW_BATTERY_SUPPORT`、`TRAN_CHARGER_KPOC_ANIMATION`** 等不会被扫到。  
2. **关机充电宏不在 MediaTek bootloader 目录**：`CUSTOM_TRAN_LOGO`、`TRAN_CHARGER_KPOC_ANIMATION`（Android/Tran 侧）在 **`vendor/transsion/projects/<BOARD>/ProjectConfig.mk`**，若检索范围只在 `mediatek/proprietary/bootloader`，会 **整类遗漏**。  
3. **与 DTS 解耦**：上述均为 makefile/ODM 宏，**内核 `battery_prop.dtsi` 里没有对应字段**，仅做 DTS 对齐无法自动发现差异。

**纠正规则**：凡「充电栈 / gauge / KPOC」迁移，必须在老新树上对上述 **Preloader mk + LK2 `<BOARD>.mk` + `ProjectConfig.mk`** 各做一次 **定向 grep + 文本比对**，并写入迁移报告。

**细则引用**：gauge 宏语义见 `mtk-adapt-template-device-gauge` § Bootloader；KPOC / `CUSTOM_TRAN_LOGO` 与 `TRAN_PRODUCT_*` 纪律见 **`transsion-sunmao40-customization-features-adapt`** **RULE-2**。

**纪律（避免重复犯错）**

1. **禁止默认新建 `preloader/.../<BOARD>_overlay.mk`**  
   - 「读不到 overlay」≠「缺文件」。新树往往把宏收敛进 **`custom/<BOARD>/<BOARD>.mk`**。  
   - 应先 grep / 读构建脚本，确认 **到底是谁 include 了谁**，再把老树的充电宏 **合并进实际生效的文件**。

2. **`inc/custom_MemoryDevice.h` 不属于充电适配**  
   - 用途：Preloader **DRAM 料号表 / BOARD_ID**，供存储器识别与自动生成工具解析。  
   - 除非用户单独要求「内存料号/BOM 与老分支一致」，否则 **不要** 把它捆进「充电迁移」任务。

3. **充电相关宏必须与 DTS 器件一致（典型翻车）**  
   - 从参考机抄来的 `<BOARD>.mk` 可能仍带 **RT6160 boost**（`RT6160=yes`、`TRAN_CHG_BOOST_IC_RT6160_I2C_ID=...`），而本项目 DTS/AP 已是 **HL7139A charge pump**。  
   - 与老分支对齐时，应在 **实际生效的 `<BOARD>.mk`** 中改为例如：  
     - `HL7139A_CHG_PUMP_SUPPORT=yes`  
     - `TRAN_CHG_PUMP_MASTER_I2C_ID=<与老分支/DTS I2C 一致>`  
   - 同时删掉已不再使用的 RT6160 相关变量与 `export` 列表中的对应项，避免 Preloader 编译进错误功率路径。

4. **LK2 `*_overlay.mk` 与 `project/<BOARD>.mk`**  
   - **`TRAN_CHARGER_KPOC_ANIMATION` 等常在 `<BOARD>.mk`**；overlay 仅当构建引用时再改。  
   - 内容多与 **KPOC/LCM/音频/haptic** 等有关，与 HL7139 宏未必同文件——以 **本工程 makefile 引用** 为准。

5. **LK2 / Preloader 中与「电量计类型」「低电启动」相关的 Tran 宏（勿与充电泵宏混淆）**  
   - `TRAN_SINGLE_GAUGE`、`TRAN_DUAL_BATTERY`：**仅在三方电量计 / 双电芯等方案下才可能需要**；MTK 内置 gauge + 单电池主流项目 **一般不要抄进 LK**。  
   - `TRAN_LOW_BATTERY_SUPPORT`：与 **电池是否支持低电启动** 等产品定义挂钩，与「是否三方 gauge」无必然关系；保留或关闭需按硬件/电池规格与用户确认。

## 本次 LJ9 迁移映射（示例）

Board: `lj9_h972`  
Chip: `mt6897`

### DTSI

- old root：
  - `\\10.205.0.144\guansen.wang\lj9-old\tran_projects\lj9\lj9_h972_e1\lj9\kernel\kernel_device_modules-6.1\arch\arm64\boot\dts\mediatek\`
- new root：
  - `\\10.205.0.144\guansen.wang\lj9\vendor\kernel\kernel_device_modules-6.1\arch\arm64\boot\dts\mediatek\lj9\`

### DWS

- kernel dws old：
  - `\\10.205.0.144\guansen.wang\lj9-old\tran_projects\lj9\lj9_h972_e1\lj9\vendor\mediatek\proprietary\tools\dct\dws\mt6897\lj9_h972.dws`
- kernel dws new：
  - `\\10.205.0.144\guansen.wang\lj9\vendor\vendor\mediatek\proprietary\tools\dct\dws\mt6897\lj9_h972.dws`

- preloader dws old：
  - `\\10.205.0.144\guansen.wang\lj9-old\tran_projects\lj9\lj9_h972_e1\lj9\vendor\mediatek\proprietary\bootable\bootloader\preloader\custom\lj9_h972\dct\dct\codegen.dws`
- preloader dws new：
  - `\\10.205.0.144\guansen.wang\lj9\vendor\vendor\mediatek\proprietary\bootable\bootloader\preloader\custom\lj9_h972\dct\dct\codegen.dws`

- preloader 充电宏（新树宜落在 **`lj9_h972.mk`**，与老 `lj9_h972_overlay.mk` 内容对齐而不是新建 overlay）：
  - `\\10.205.0.144\guansen.wang\lj9\vendor\vendor\mediatek\proprietary\bootable\bootloader\preloader\custom\lj9_h972\lj9_h972.mk`

### LK2 与 Tran 工程（关机充电 / gauge 宏）

- lk2 **主工程**（必与老树 diff：`TRAN_CHARGER_KPOC_ANIMATION`、`TRAN_SINGLE_GAUGE`、`TRAN_DUAL_BATTERY`、`TRAN_LOW_BATTERY_SUPPORT` 等）  
  - old：`\\10.205.0.144\guansen.wang\lj9-old\tran_projects\lj9\lj9_h972_e1\lj9\vendor\mediatek\proprietary\bootable\bootloader\lk2\project\lj9_h972.mk`（路径随老树裁剪调整）  
  - new：`\\10.205.0.144\guansen.wang\lj9\vendor\vendor\mediatek\proprietary\bootable\bootloader\lk2\project\lj9_h972.mk`

- **`ProjectConfig.mk`（`TRAN_CHARGER_KPOC_ANIMATION`、`CUSTOM_TRAN_LOGO`）**  
  - new：`\\10.205.0.144\guansen.wang\lj9\vendor\vendor\transsion\projects\lj9_h972\ProjectConfig.mk`  
  - old：在 `<OLD_ROOT>` 下搜索上述宏所在文件（层级可能是 `vendor/transsion/projects/<BOARD>/`）

## GPIO 核对清单（充电/电源常用）

迁移充电栈时至少核对以下引脚：
- `25, 27, 28, 29, 42, 61, 132, 136, 137, 138, 227`

核对要求：
- 新树 DTSI 中引用的 GPIO 必须存在。
- DWS 的 mode/direction/eint 属性需与老板意图一致。
- 若 copy 后仍不一致，按具体 gpio 节点补丁修正新 DWS，并再次回读确认。

### `protocol_ta.dtsi` 与 TFCP I2C：`varName0`（kernel + preloader DWS）

若板级目录存在 **`protocol_ta.dtsi`**（典型在 `.../mediatek/<board>/protocol_ta.dtsi`），其中 **`&i2cN { tfcp_ta@... }`** 定义了 TFCP TA 的 I2C 挂载总线。该总线上的 **SCL/SDA 对应哪两个 GPIO**，板级 fragment 往往不写全，需在 **芯片平台基 DTS** 里查对应 **`i2cN`** 节点属性：

- 常见属性名：`**scl-gpio-id**`、`**sda-gpio-id**`（值为 GPIO 编号，与 DWS 里 `<gpioM>` 一致）。
- 示例（MT6897，`i2c12`）：平台文件 `arch/arm64/boot/dts/mediatek/mt6897.dts` 中 `i2c12: i2c@...` 含 `scl-gpio-id = <161>;`、`sda-gpio-id = <162>;`（具体编号随 SoC/控制器变化，**以当前芯片平台 dts 为准**）。

**DWS 规则（Tran / charge pump 相关命名，必做）：**

- 在 **kernel DWS**（`tools/dct/dws/<chip>/<BOARD>.dws`）与 **preloader DWS**（`preloader/custom/<BOARD>/dct/dct/codegen.dws`）中，对上述 **两只 I2C 脚** 各自增加 **`<varName0>`**：
  - SCL 对应 GPIO 节点：`TRAN_CHGPUMP_SCL_PIN`
  - SDA 对应 GPIO 节点：`TRAN_CHGPUMP_SDA_PIN`
- 若 `protocol_ta` 挂在 **`&i2cN` 且与 HL7139 等 charge pump 共用同一总线**，仍按该 **`i2cN`** 在平台 dts 中的 `scl-gpio-id` / `sda-gpio-id` 落位上述 `varName0`（与 CP 器件同路 I2C 的物理脚一致）。

迁移或适配输出中，在 **GPIO 一致性** 小节应写明：`protocol_ta` → `i2cN` → 平台 dts 行号/属性 → DWS `gpio` 编号 → 是否已写 `varName0`。

## 如何确认“充电实际用了哪些 GPIO”

不要只看固定清单，必须按以下规则动态提取：

1. **先定文件范围（充电主链）**
   - 必查：`tc_charger.dtsi`、`tc_pe50.dtsi`、`tran_usb_ctrl.dtsi`、`tc_hl7139a.dtsi`、`cps4021.dtsi`、`tc_wireless_chg.dtsi`、`tran_led*.dtsi`、`aw20144.dtsi`、**`protocol_ta.dtsi`**（TFCP TA I2C；GPIO 编号见芯片平台基 dts 中对应 `i2c` 的 `scl-gpio-id` / `sda-gpio-id`，DWS 须配 `TRAN_CHGPUMP_SCL_PIN` / `TRAN_CHGPUMP_SDA_PIN`，见上文「protocol_ta.dtsi 与 TFCP I2C：`varName0`」）
   - 还要检查 board dts 的 include，避免遗漏同层 dtsi

2. **从 DTSI 抓 GPIO 号**
   - 抓 `<&pio N ...>`：统计所有 `N`
   - 抓 `PINMUX_GPIOxxx__FUNC_...`：提取 `xxx`
   - 抓 `*-gpio` / `*-gpios` 属性：确认是输入中断还是输出控制

3. **按功能分组（必须输出）**
   - `中断类`：如 `hl7139a,intr-gpios`、`eint_*`
   - `控制类`：如 `enable-gpio`、`control_gpio`、`sleep-gpios`、`dv_vctrl-gpios`
   - `DP/DM握手类`：`tran_usb_ctrl` 里的 `PINMUX_GPIO137/138...`

4. **与 DWS 交叉校验**
   - kernel dws：核对 `<gpioN>` 的 `eint_mode/def_mode/def_dir/inpull/smt/ies`
   - preloader dws：至少核对同一 `gpioN` 的 `def_mode/def_dir/eint_mode`
   - 任一侧缺失或冲突都标记为 `mismatch`

5. **输出标准**
   - 给出三类结果：`一致` / `遗漏` / `不一致`
   - 每个 GPIO 必须带“来源证据”（DTSI 属性名 + DWS 节点）
   - 不允许只给结论不列证据

## 充电参数迁移关键点（本次实战补充）

以下条目在迁移时必须单独核对，不可默认“按旧树整包拷贝”或“按平台默认”：

1. **OVP 与 VBUS 测量策略要成组核对**
   - 必查：`charger_voltage_ovp`、`vbus_measure_method`、`tc_misc` 中 `det_vbus_by_dvchg`
   - 规则：若用户只要求恢复部分项（如 ADC 通道/分压），不要擅自联动改其它项
   - 输出时要明确说明哪些项保持老值、哪些项按新平台策略保留

2. **`tc_misc` 恢复要避免“超额修改”**
   - 常见项：`io-channels`（VIN4/VIN5/VIN7）、`tusb_div_vol`、`det_vbus_by_dvchg`、`det_ibus_by_swchg`
   - 规则：仅按用户明确要求改动；如果做一致性联动，必须先与用户确认

3. **Gauge 参数统一用新口径：`r-fg-value`**
   - 不再推荐继续使用 `R_FG_VALUE` 旧写法
   - 按当前 Transsion/MTK 口径，配套核对：
     - `r-fg-value`
     - `rfg-mtk-tran-conf-diff`
   - 建议同步保留 Rfg 说明注释（mtk/transsion 映射关系）

4. **`battery_table.dtsi`：`profile-t{m}-num` 必须与数据行数一致**
   - 文件：`.../bat_setting/*battery_table*.dtsi`（如 `mt6897_battery_table.dtsi`）
   - 规则：每个 `battery{n}-profile-t{m}-num`（或项目命名的 `battery2-profile-t*-num`）必须等于该块 `< ... >` 内**数据行数**（常见事故：从老树/参考机多拷了行却未改 `-num`，或 `-num` 仍为模板默认 `100`）。
   - 迁移输出须写明：各 `t{m}` 的 `-num` 与数行结果 **`match / mismatch`**（若 mismatch 必须先修正再合入）。

5. **`single_batt_level*` 与 `step_ffc_level*` 必须逐段比对**
   - `tc_charger.dtsi`：`single_batt_level_0 ... N`、`single_batt_level`
   - `tc_pe50.dtsi`：`pe5_ffc_gap`、`step_ffc_level_0 ... N`
   - 规则：至少做“逐段文本比对”，不要只看层级是否存在

6. **DWS 同步后仍需二次回读核对**
   - 即便执行了 copy，也可能出现关键 GPIO 未按老值落地
   - 规则：对关键 GPIO（如 25/27/28/29/42/61/132/136/137/138/227）逐个回读确认
   - 若不一致，按节点补丁修正并再次回读

7. **Preloader `<BOARD>.mk` 充电宏与 DTS CP 器件对齐**
   - 核对：`DV2_CHG_SUPPORT`、`TRAN_PL_POWER_ARCH_SUPPORT`、`MTK_EXT_CHGDET_SUPPORT`、以及 **CP/boost 器件宏**（HL7139A vs RT6160 等）与 `export` 列表一致
   - 禁止：AP DTS 已是 HL7139A，Preloader 仍 export RT6160 变量

## KO 打包/编译适配（必须单独检查）

DTSI 对齐不代表可出包，迁移时必须同步核对以下三层：

1. **老路径内核配置层（用于理解“有哪些功能/ko 被打开”）**
   - 说明：新路径不走内核 config 控制编译；此处只用于从老树提取“开启了哪些功能/模块”作为迁移基线。
   - 老路径常见：`<OLD_ROOT>/kernel/kernel_device_modules-<KDM_VER>/kernel/configs/tran_custom.config`
   - 检查规则：
     - 抽取充电链路关键 `CONFIG_` 项（如 `CONFIG_TC_CHARGER`、`CONFIG_TCHARGER_HL7139A`、`CONFIG_CHARGER_CPS4021`、`CONFIG_TC_LEDS_AW20144` 等）
     - 结合驱动 Makefile/Kconfig，建立 “CONFIG -> 影响的 ko/功能” 对照（用于后续对 csv/ko 列表的完整性校验）

2. **Kleaf 模块收集层（是否打进 modules list）**
   - 老路径常见（旧树通过 bzl 列表收集 ko）：
     - `<OLD_ROOT>/kernel/kernel_device_modules-<KDM_VER>/kernel/kleaf/tran_custom_modules.bzl`
   - 新路径关键位置：
     - `<NEW_ROOT>/vendor/kernel/kernel_device_modules-<KDM_VER>/drivers/power/supply/transsion/BUILD.bazel`
     - `<NEW_ROOT>/vendor/kernel/kernel_device_modules-<KDM_VER>/kernel/kleaf/mgk_64.bzl`
   - 检查规则：
     - 先从老 `tran_custom_modules.bzl` 抽出充电相关 `*.ko` 期望列表（旧基线）
     - 确认 transsion 充电相关模块在 Bazel 侧可被 build（目标/列表存在）
     - 与 `ko_order_table.csv`（或项目 ko 清单）交叉校验：csv 列出的 ko 必须在 Bazel 规则可产出

### KO 适配输出要求

- 单独增加 `KO 编译与打包一致性` 小节，至少列出：
  - `仅老有` / `仅新有` / `两边一致` 的 ko 条目
  - 老路径 `CONFIG_` 对应到 ko/功能的映射与差异点（用于解释“为什么要增删某个 ko”）
  - 是否需要用户决策（保留老行为还是升级到新平台策略）

## 输出格式

建议使用以下分段：
- `路径映射确认`
- `DTSI 迁移结果`
- `DWS 同步结果`
- `GPIO 一致性`（充电相关 DTSI 引脚与 kernel/preloader DWS 交叉核对）
- `Preloader <BOARD>.mk（充电泵等）与 DTS 器件一致性`
- `LK2 project/<BOARD>.mk（gauge 类宏、TRAN_CHARGER_KPOC_ANIMATION 等）老新 diff`
- `Tran ProjectConfig.mk（TRAN_CHARGER_KPOC_ANIMATION、CUSTOM_TRAN_LOGO）老新 diff`
- `battery_table.dtsi`：`battery{n}-profile-t{m}-num` 与各温区数据行 **match/mismatch**
- `KO 编译与打包一致性`（若适用）
- `风险项`（如路径不可达、复制后无法校验）

## 约束

- 不要修改无关 worktree。
- 不要假设 shell copy 成功；必须回读目标文件。
- **不要为了「补齐文件」而新建 `*_overlay.mk`**；充电相关变更优先落在构建链 **实际 include** 的 `<BOARD>.mk`（或用户指定的 makefile）。
- **`custom_MemoryDevice.h` 仅在用户明确要求内存料号迁移时修改**，不默认随充电任务改动。
- 若 old/new 的 chip 或 board 不同，先暂停并向用户确认跨平台迁移策略。

