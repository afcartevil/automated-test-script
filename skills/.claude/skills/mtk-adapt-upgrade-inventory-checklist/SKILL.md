---
name: mtk-adapt-upgrade-inventory-checklist
description: 老分支升级柱0信源清单：OLD_TRAN_ROOT 与新侧路径拼凑、DWS 映射与 GPIO 溯源；A.3 柱2节点闸门索引；A.4 柱2映射完成后反填 rg。与编排器三柱模型对齐。
---

# MTK 升级适配：Inventory 清单

## 状态

**柱 0**（A.1/B.1、DWS 工作流、路径纪律）与 **A.3（柱 2 闸门索引）** 已可执行。**块 E / 块 F** 等仍为骨架，供按三柱模型填补。

## 用途与三柱模型

本 skill 主要服务 **`mtk-adapt-upgrade-branch-orchestrator` 柱 0**：**老新信源对照**与**可追溯文件列表**，供 **柱 1（器件）**、**柱 2（参数）** handoff。

- **柱 1～3 的落盘步骤**：一律经 **`mtk-adapt-template-router`** → `mtk-adapt-template-device-*` / `mtk-adapt-template-basic-charging-capability` / **`transsion-sunmao40-customization-features-adapt`**（**柱 3** 以 **口述** 为主、可选 **`pillar3-customization-input.md`**，见合并 skill **RULE-0**；口述与表均未给出「要做」项则停柱 3）。本清单 **不**重复器件 IC 细节或特性实现。

### 路径与搜索纪律（与编排器一致）

- **新侧**：先按 `mtk-adapt-upgrade-branch-orchestrator` **路径解析纪律** 与 `mtk-adapt-template-device-pd-ic` / `charge-pump` §0.1～0.3 拼出 `project_full`、DWS、`tc_charger_lk.dtsi` 等路径，再 `Read` / 在**已确定目录**下列举。  
- **禁止**依赖对整棵 AOSP 或整棵内核树的无边界 `grep` 来反推项目目录。  
- **A.4** 的 `rg` 建议仅在 **柱 2 参数/DTSI 映射冻结后** 由执行者整理填入，且 **仅**在已拼出的子路径内使用。

---

## 块 A — Kernel / KDM 树

### A.1 新老信源根路径（柱 0）

**老分支（用户输入）**

- 用户给出 **`OLD_TRAN_ROOT`**：老方案仓库下 **`tran_projects/<系列>/<具体工程目录>/<与 vendor 同级目录>`** 形式的根（示例形态：`tran_projects/lj9/lj9_h972_e1/lj9`）。  
- 在该根下通常可找到：**充电相关 dtsi**、**LK mk**、**preloader mk**、**DWS** 等；Inventory **从该根列举**老侧文件，**不**依赖全树反推项目名。

**新分支（skill 拼凑，不写死全树 glob）**

- 按 **`mtk-adapt-upgrade-branch-orchestrator` 路径解析纪律** + **`mtk-adapt-template-device-pd-ic` / `device-charge-pump` / `device-charger-ic` / `device-gauge`** 等 **§0.x** 拼出：`project_full`、`kernel_dws_path`、`preloader/custom/<project_full>/.../codegen.dws`、`tc_charger_lk.dtsi`、`mediatek/charge/<project_full>/` 等待适配路径。

### A.2 老分支充电相关 dtsi 命名（柱 0）

老树可能已是 **`tc_*`** fragment（与新侧同族），也可能仍为 legacy 名，例如 **`tran_charger.dtsi`**、**`tcpc_config.dtsi`**、**`mtk_pe50.dtsi`** 等。在 **`OLD_TRAN_ROOT`** 下列举时 **两族都要覆盖**；并顺着 **`#include` 链** 展开 fragment，避免只扫板级入口。

### A.3 柱 2：老 KDM 节点 / 文件名闸门（handoff 索引）

以下条目为 **参数与语义迁移** 规则索引；正文以 **`transsion-charger-dtsi-driver-bridge`**、**`transsion-tran-battery-to-tc-charger-dtsi`**、**`transsion-pe5-migrate-dual-cp-k612`** 及编排器 **§5～§13** 为准。

**与 `tran_battery` 的衔接（调用规则）**：清单中若将 **`tran_battery`（`tran,chg_fun`）** 或同文件 **`jeita_*_chg_cur` / `pcb_*`** 标为需迁往新树 **`&charger`**，在 handoff 给 **`mtk-adapt-upgrade-branch-orchestrator`**（**柱 2** / 阶段 3～3B）时，**须写明**：执行者 **`Read` `transsion-tran-battery-to-tc-charger-dtsi` 全文** 后再出 `tc_charger.dtsi` 片段（**不得**假设用户单独 @ 该 skill）。反向 **新→老** 落盘时仍 Read 该 skill 作语义源，再逆变换。

**`tran_battery_aging`（`tran,chg_aging`）**：老 KDM 常见 **`tran_battery_aging { compatible = "tran,chg_aging"; battery_aging_module0..3; }`**。新分支 **不要**、**无 DTS 字段迁移**；清单中记为 **「命中即忽略」**——handoff 编排器时 **不**列为迁移任务、**不**要求用户确认模块号映射（与 **`mtk-adapt-upgrade-branch-orchestrator` §5**、**`transsion-tran-battery-to-tc-charger-dtsi` §0** 一致）。

**`tran_otg`（`tran,otg_fun`）**：**仅 老 → 新**。handoff 须写明：老树 **核对 `compatible`**；**6.12 比老树多出的属性** 老树未配时 **用 bridge 表默认 + `mtk-adapt-template-basic-charging-capability` 的 `tran_otg` 模板补全**；**`otg_boost_*`→`tc_otg_boost_*`**；产出后 **模板补全及 PD/boost/温控 相关项全量 `[REVIEW]`**（见 **`transsion-charger-dtsi-driver-bridge`**「**`tran_otg` 迁移工作流**」与 **`mtk-adapt-upgrade-branch-orchestrator` §6**）。**不涉及新→老 OTG 落盘。**

**`tran_auto_test` → `tc_auto_test`**：老 **`compatible = "tran,auto_test"`**、节点 **`tran_auto_test`** → 新 **`"tc,auto_test"`**、**`tc_auto_test`**；同步 **`&tran_auto_test`** 等 phandle；见 **`transsion-charger-dtsi-driver-bridge`** 与编排器 **§7**；**`[REVIEW]`** **`rg "tran,auto_test|tran_auto_test"`**。

**`water_detect`（`transsion, water_detect`）**：**compatible 不变**；**`scheme` 非 0/1 时** 须按 **5.10→6.12 对照表** 改写（**老 4→新 2** 等）；**`bootmode = <&chosen>`** 新侧 **不解析**，可删；**`polling_interval` / `gpio_*`** 仍有效；见 **`transsion-charger-dtsi-driver-bridge`**「`water_detect`」与编排器 **§8**；**`[REVIEW]`** **`scheme`≥2 或 SBU 组合** 实机。

**`pid_chg`（`tran,pid_chg_algo`）**：迁到新 KDM 时 **`compatible` → `tc,pid_chg_algo`**；补 **`ambient_temp`**、**`target_temp_array`**（与 **`power_level` 五档** 对齐，老树常无）；其余字段多 **直拷**；见 **`transsion-charger-dtsi-driver-bridge`**「`pid_chg`」与编排器 **§9**；**`[REVIEW]`** **`rg "tran,pid_chg_algo"`** 与亮屏温升/限流手感。

**`ambient_detect` / `temp_forecast`**：**`transsion,ambient_detect`→`tc,ambient_detect`**、**`transsion,temp_forecast`→`tc,temp_forecast`**；**`ambient_detect`** 多 **整段直拷**；**`temp_forecast`** 补 **`pa_temp_gap`**（老树无则默认 **`<500>`**，有量产基准则从基准）、核对 **`machine_gap`** 去留、**`orgin_rate` 保留产品值**；见 **`transsion-charger-dtsi-driver-bridge`** 与编排器 **§10**；**`[REVIEW]`** **`rg "transsion,ambient_detect|transsion,temp_forecast"`**。

**`support_alg` 子节点（`&pe2`/`&tc30`/…）**：板级 overlay 改 **`&tc_pe2`/`&tc_30`/`&tc_hvdcp20`/`&tc_pd`**；**`*_ichg_level_threshold`→`ta_ichg_level_threshold`**；**`vbat_threshold`×1000**；**`sc_*`→`chr_volt*`**；**`pdc`：`sc_charger_current`→`charger_current_limit`**；双串/线缆阻抗等 **`[REVIEW]`**；见 **`transsion-charger-dtsi-driver-bridge`** 与 **`transsion-dcp-fastcharge-probe`**、编排器 **§11**。

**`extcon_usb`**：**完全按新分支**；**6.12** 为 **Transsion extcon**（`compatible` 以 SoC 基准为准），**非 6.12** 常见 **`mediatek,extcon-usb`**；**`charger`：`&switch_chg`→`&tc_chgtype`**；**`remote-endpoint`** 从 **芯片平台基准 dtsi** 解析；见 **`transsion-charger-dtsi-driver-bridge`**、编排器 **§12**。

**`&pe5` / `mtk_pe50.dtsi`（`mediatek,charger,pe5`）→ 新树 `tc_pe5`**：Inventory 命中老树 **`&pe5`**、**`mtk_pe50.dtsi`** 或 **`compatible = "mediatek,charger,pe5"`**，且升级目标含 **`kernel_device_modules-*`/transsion `tc_pe5.c`** 时，handoff **`mtk-adapt-upgrade-branch-orchestrator`**（**柱 2** / 阶段 3～3B）**须写明**：执行者在写 **`tc_pe5.dtsi` / `&pe5` 片段** 前 **必须 `Read` `transsion-pe5-migrate-dual-cp-k612`**（热限 **`*_curlmt` 与老栈 dual/third 路径下 ×2 语义、新栈不 ×2、`conversion_ratio` 与 FFC 分工）；**不得**仅依赖 **`transsion-charger-dtsi-driver-bridge`** 处理数值。编排器路径纪律见 **§13**。

### A.4 搜索关键字（rg 建议 · 柱 2 收口）

**在柱 2（DTSI 参数/节点映射）冻结后**，由执行者根据映射结果整理「关键字 / 含义 / 允许 `rg` 的子目录（`OLD_TRAN_ROOT` 下老路径或新侧已拼目录）」填入本节。**禁止**全树探针。初期可 **留空表头**，待项目填补。

---

## 块 B — LK / Bootloader（柱 0 + 柱 1 入口）

### B.1 LK dtsi / mk / 入口（路径同 A.1）

- **老侧**：在 **`OLD_TRAN_ROOT`** 下列举 LK 相关 **dtsi / mk / 规则文件**。  
- **新侧**：按编排器路径纪律 + **`mtk-adapt-template-device-charger-ic`** 中 **`tc_charger_lk.dtsi` 路径规则** 拼凑并 `Read`。  
- LK 与 kernel **重复参数以谁为准**：以 **`device-charger-ic` / `mtk-adapt-template-basic-charging-capability`** 既有约定为准（本清单不展开）。

#### B.1.1 Preloader / LK2 顶层 `*.mk` 对照（通用 + lj9 实例）

升级时 **老新各自真实参与编译的 mk 文件名可能不同**（常见老侧 `*_overlay.mk`、新侧去掉 `_overlay` 或合并到目录内主 mk）。Inventory 须在简报中 **老一行、新一行** 写清。

**实例（lj9_h972，用户定稿）**：

| 层级 | 老（相对 `OLD_TRAN_ROOT`） | 新（相对新 AOSP 根） |
|------|-----------------------------|----------------------|
| Preloader | `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/lj9_h972/lj9_h972_overlay.mk` | `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/lj9_h972/`（以目录内实际 **主 mk** 为准，如存在 `lj9_h972.mk` 则写明） |
| LK2 | `vendor/mediatek/proprietary/bootable/bootloader/lk2/project/lj9_h972_overlay.mk` | `vendor/mediatek/proprietary/bootable/bootloader/lk2/project/lj9_h972.mk` |

**实例（cl6 → `cl6k_h898`，老根 `tran_projects/cl6/cl6_h898_a1_cl6k_v/cl6`）**：

| 层级 | 老（相对 `OLD_TRAN_ROOT`） | 新（相对新 AOSP 根） |
|------|-----------------------------|----------------------|
| Preloader | `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/cl6_h898/cl6_h898_overlay.mk` | `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/cl6k_h898/cl6k_h898.mk`（同目录另有 `makefile`、`cust_bldr.mak`、`dct/dct/codegen.dws` 等） |
| LK2 | `vendor/mediatek/proprietary/bootable/bootloader/lk2/project/cl6_h898_overlay.mk` | `vendor/mediatek/proprietary/bootable/bootloader/lk2/project/cl6k_h898.mk` |

其它项目复制本表头，替换 **`<老 preloader 目录>/<老 overlay mk>`** 与 **`<新 project_full>/`** 即可。

#### B.1.2 柱 1 必选：Preloader / LK2 `*.mk` 核对（与 dtsi 同级）

柱 1 **不得**只做 kernel dtsi；**须**在 **`OLD_TRAN_ROOT`** 与新 AOSP 根下各打开 **实际参与编译** 的：

| 检查项 | 老侧（`OLD_TRAN_ROOT` 起算） | 新侧（编排器路径纪律 §1） | 通过准则 |
|--------|------------------------------|-----------------------------|----------|
| Preloader 主 mk | `preloader/custom/<老 project_full>/` 下 **overlay 或主 mk**（以老工程 **真正 include 的顶层 mk** 为准） | `preloader/custom/<新 project_full>/` 下 **主 `*.mk`** | **宏名/开关** 与 **充电器件、gauge、双电池** 选型一致；无「老树开、新树关」的 **静默遗漏** |
| LK2 工程 mk | `lk2/project/<老 project_full>_overlay.mk` 或等价 | `lk2/project/<新 project_full>.mk` | **`tc_charger_lk.dtsi`** 路径、**`TRAN_*`** 与 **`mtk-adapt-template-basic-charging-capability`**「**`tc_charger_lk` 强约束**」一致；与 kernel **`tc_charger.dtsi`** 不矛盾 |

**简报须附**：老新各 **一行路径**（preloader mk、lk2 mk）+ **是否已 Read**；异常项标 **`[REVIEW]`** 并指向 **`mtk-adapt-template-device-charger-ic` / `device-gauge`**。与 **`mtk-adapt-upgrade-branch-orchestrator` §3.1** 柱 1 清单一致。

### B.2 与 gauge / charger 等器件相关的宏（柱 1）

**不**在本 skill 维护宏大全。确定器件类别后 **`Read` 对应 `mtk-adapt-template-device-gauge` / `device-charger-ic` / `device-pd-ic` / `device-charge-pump`**，按各 SKILL 处理 **ProjectConfig.mk、TRAN_*、LK** 等。

---

## 块 C — Preloader（柱 0 + 柱 1）

### C.1 `codegen.dws` / DWS 引脚（柱 0）

**同步准则**：对 GPIO 溯源表已对齐的 **同一 GPIO**，**新分支** kernel DWS 与 preloader **`codegen.dws`** 中相应引脚配置 **应与老分支一致**（模式/上下拉/EINT 等）；用户声明 **换板/换料** 的脚位除外，以硬件与 dtsi 为准（衔接编排器路径纪律 **§4**）。

**DWS 的完整路径模板、GPIO 溯源表** 见下文 **「DWS 映射模板与同步工作流」**（与 `mtk-adapt-template-device-charge-pump` 中 TFCP / `protocol_ta` 等交叉引用）。**RFC / TA 硬件与 I2C/DWS**：**先按 `mtk-adapt-template-device-charge-pump`** 执行；不足处由项目补充后再改本 skill。

### C.1.1 与 kernel DWS 的关系

- **Kernel DWS** 与 **preloader `codegen.dws`** 为两套文件；充电/TFCP 相关脚位须在两侧 **分别核对**，并与 **kernel dtsi 中 `&pio` / `*-gpios` / `pinctrl`** 一致。

### C.2 preloader 阶段 charger IC 相关配置（柱 1）

指 preloader 树内与 **charger IC** 相关的配置（具体路径随仓库，仍在 **`OLD_TRAN_ROOT`** 下可见）。**执行方式同 B.2**：先确定 **charger IC**，再 **`Read` `mtk-adapt-template-device-charger-ic`** 按其中 **preloader / bootloader** 章节适配。

---

## DWS 映射模板与同步工作流（必守）

做 **DWS 同步**（老分支 → 新分支）时，**禁止**在未完成 **GPIO 溯源表** 的情况下直接整文件拷贝或仅做 XML diff 合并。必须先 **列表**，再 **前后对比**。

### 1) 目录映射模板（老 `tran_projects` → 新 AOSP 根）

以下占位符与 `mtk-adapt-template-device-pd-ic` §0.1～0.3 一致：

- **`${MTK_PLATFORM_LOWER}`**：由 `vendor/transsion/projects/<project_full>/ProjectConfig.mk` 中 `MTK_PLATFORM` 转小写（如 `MT6789` → `mt6789`；**注意** 与芯片目录一致，如 mt6878 项目则用 `mt6878`）。
- **`${PROJECT_FULL}`**：`vendor/transsion/projects` 下项目目录全名（如 `x6876_h786`、`cl6k_h898`）。
- **`${OLD_TRAN_ROOT}`**：老方案仓库根（含 `tran_projects/.../x6876` 或 `cl6` 等 **直至其 `vendor` 同级** 的路径，以你本地检出为准）。

| 目标文件 | 升级前（老分支侧，模板） | 升级后（新分支 AOSP 根下，模板） |
|-----------|---------------------------|-----------------------------------|
| **Kernel DWS** | `${OLD_TRAN_ROOT}/vendor/mediatek/proprietary/tools/dct/dws/${MTK_PLATFORM_LOWER}/${PROJECT_FULL}.dws` | `vendor/mediatek/proprietary/tools/dct/dws/${MTK_PLATFORM_LOWER}/${PROJECT_FULL}.dws` |
| **Preloader `codegen.dws`** | `${OLD_TRAN_ROOT}/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/${PROJECT_FULL}/dct/dct/codegen.dws` | `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/${PROJECT_FULL}/dct/dct/codegen.dws` |

**示例（仅说明形态，路径以实际检出为准）**

| 说明 | 升级前 | 升级后 |
|------|--------|--------|
| x6876 / mt6878 | `tran_projects/x6876/x6876_h786_a1/x6876/vendor/.../dws/mt6878/x6876_h786.dws` | `vendor/.../dws/mt6878/x6876_h786.dws` |
| CL6K / mt6789 | `tran_projects/cl6/cl6_h898_a1_cl6k_v/cl6/vendor/.../dws/mt6789/cl6_h898.dws`（老项目名可能与 `${PROJECT_FULL}` 不同，以老树 **实际文件名** 为准） | `vendor/.../dws/mt6789/cl6k_h898.dws` |

若老侧 **`${PROJECT_FULL}.dws` 文件名与升级后不一致**（如 `cl6_h898` vs `cl6k_h898`），须在同步说明中 **显式写两行路径**，不得默认同名。

### 2) DWS 同步前强制：GPIO 溯源表（先列表，再对比）

在修改任一侧 DWS 之前，输出 **同一张表**（可先 Markdown / 简报），包含 **至少** 充电链路相关 GPIO（含 TFCP / CP SCLSDA、`varName0`/`varName1` 涉及脚、各 charger/tcpc/cp IRQ 脚等），再扩展到本次改动波及的其它脚。

**必填列：**

| 列名 | 含义 |
|------|------|
| **GPIO 号** | 如 GPIO4、与 dtsi 中 `&pio N` 一致 |
| **证据来源** | **从哪里来**：例如 `charge/<project>/sc8950.dtsi` 中 `sc8950,intr_gpio = <&pio 4 ...>`；或原理图页码/网络名（若 dtsi 未显式写号，须注明推导链） |
| **作用** | **是什么**：如 SC8950 ALRT、RT1711 IRQ、HL7139 主/从 INT、TFCP GPIO-I2C SCL/SDA、USB ID 等 |
| **Kernel DWS 老** | 老 `*.dws` 中该 GPIO 关键项摘要：`eint_mode`、`def_mode`、`varName0/1`、上下拉等（可贴片段或文件:行） |
| **Kernel DWS 新** | 新 `*.dws` 同 GPIO 摘要 |
| **Preloader codegen 老** | 老 `codegen.dws` 同 GPIO 摘要（若与 kernel 要求一致，可写「同 kernel」） |
| **Preloader codegen 新** | 新侧摘要 |
| **前后一致** | 是 / 否 / 待确认 |
| **备注** | 若否：计划修改侧（仅 kernel / 仅 pl / 两侧）与原因 |

**纪律：**

1. **先**填「GPIO 号 + 证据来源 + 作用」，从 **dtsi / `tc_*` fragment** 与 **`mtk-adapt-template-device-*`** 要求导出脚位，**再**打开两侧 DWS 填对比列。  
2. **再**做老 vs 新 XML 对比；若与溯源表冲突，**以溯源表 + 硬件为准**，并更新备注。  
3. 对 **`TRAN_CHGPUMP_SCL_PIN` / `TRAN_CHGPUMP_SDA_PIN`**（或与 `protocol_ta` 共用 I2C）：须写清 **与 `protocol_ta.dtsi` / 平台基 dts `scl-gpio-id`/`sda-gpio-id` 的对应关系**（见 `mtk-adapt-template-device-charge-pump`）。  
4. 未覆盖的 GPIO **不得**假设「与充电无关」即省略；若本次同步范围不含某脚，在表中单独 **标记范围外**。  
5. 若溯源表已证明新侧 dtsi/DWS 仅 **硬件静态描述笔误**（如 I2C 从地址与老树/BOM 不一致），可按 `mtk-adapt-upgrade-branch-orchestrator` **路径纪律 §4** 直接在新树修正并与老分支对齐，**落盘后告知**；仍建议在溯源表中 **更新一行** 记录该修正。

- [ ] Kernel DWS 与 **所有** 相关 `*.dtsi` 中 `*-gpio*` / `pinctrl` 一致  
- [ ] Preloader `codegen.dws` 与 Kernel DWS 对 **同一 GPIO** 的命名/模式 **无矛盾**  
- [ ] 已存档：GPIO 溯源表路径或粘贴至升级简报「DWS」节  

---

## 块 D — 构建与打包（提示）

### D.1 defconfig / fragment / Makefile（柱 2 异常时）

**仅提示**：若 DTS/DWS 已对齐仍出现 **充电 ko 未进镜像 / 模块未加载**，再到 **`kernel_device_modules-*`** 下按项目查 **defconfig / fragment / Makefile**。不在本 skill 展开逐条 `CONFIG_*` 清单。

### D.2 `ProjectConfig.mk`（随柱 1～3 收口）

充电 / KPOC / 工模 / gauge 类型等相关宏，**随 `mtk-adapt-template-router` 三柱** 在各自 **`device-*` / `feature-*`** SKILL 中落地。**器件柱完成后可选**：老新 **`vendor/transsion/projects/<project_full>/ProjectConfig.mk`**（及老侧等价 mk）**diff**，查 **未被已执行 skill 覆盖的游离行**。

---

## 块 E — 常见遗漏清单（勾选表）

（预留：表格列「检查项 | 已扫/未扫 | 备注」。）

---

## 块 F — Inventory 输出模板

（预留：orchestrator 第 2 步期望的「文件路径 + 一句话角色」列表模板。）

---

## 修订记录

| 日期 | 摘要 |
|------|------|
| 2026-05-12 | DWS 溯源纪律第 5 条：与 `mtk-adapt-upgrade-branch-orchestrator` §4（硬件强相关可直接对齐老分支）衔接。 |
| 2026-05-12 | **B.1.1**：增加 **cl6k_h898** 与 **cl6_h898** 老根对照及新侧 **`cl6k_h898.mk`** 文件名；**lj9** 新侧列补充「若有 `lj9_h972.mk` 则写明」。 |
| 2026-05-13 | **A.3 `temp_forecast` / `pa_temp_gap`**：老树无则默认 **`<500>`**（有量产基准则从基准）。 |
| 2026-05-13 | **B.1.2**：柱 1 必选 **Preloader / LK2 `*.mk` 核对表**；与 **`mtk-adapt-upgrade-branch-orchestrator` §3.1** 对齐。 |
