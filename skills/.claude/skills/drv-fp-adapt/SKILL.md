---
name: drv-fp-adapt
description: 
  指导 Transsion/MTK Android 升级项目 vendor 侧指纹 P1 适配：归一化与非归一化判定、驱动 compatible、DTS/DWS、工模与 Sensor.json、KO/ProjectConfig/device-vext、ODM TA 与指纹库路径。当用户要进行**指纹 P1 调试**、**榫卯迁移**或**驱动/库适配**，且提供或愿意补充**目标项目代号**（如 LJ8、X6876、X6885、CM5）、**平台/SoC**（如 MT6878、MT6789）、**kernel_device_modules 版本**（如 kernel-6.1、kernel-6.12）、**指纹 IC 厂商与型号**（如 GOODIX GW9598、ANC、Silead）时使用；执行时以用户指定目标项目和升级前代码为落地边界，不因复用机型名或参考案例名修改其他项目目录；主 SOP https://transsioner.feishu.cn/wiki/A74wwMGsLiTCBXkMJjVccUDfnKd；CM5/X6885/归一化榫卯子文档与 EXTENSION_*.md 见 SKILL 正文。
---

# DRV_FP_Adapt — 升级项目指纹 P1 调试

业务命名：**DRV_FP_Adapt**。本 Skill 以**主文档**（上节链接）为**主要调试依据**；与「仅日志定位」类 Skill 互补，验证可结合 `android-fingerprint-log-analysis`。主文档**第三节**所链三篇飞书及 **EXTENSION_*.md** 为**参考材料**（典型案例与补充细节）。

**当前版本**：`1.1.6`（正式版）。版本号、发布状态与维护规则见 [VERSION.md](VERSION.md)；变更历史见 [CHANGELOG.md](CHANGELOG.md)。

用户提到**指纹调试**时 Agent **应优先**按本 Skill 执行。**推荐一次说清**：项目代号、平台（SoC）、`kernel_device_modules` 版本、**指纹 IC** 厂商与型号（如 GOODIX GW9598）、已知则补充归一化/非归一化。示例：「我现在要进行X6876项目的 **指纹** P1调试，该项目平台是 MT6878，kernel版本是 kernel-6.1，指纹采用GOODIX， 型号是 GW9598。」信息不全时可先追问关键信息再按本Skill执行。

**项目落地边界**

- 必须先确认用户指定的**目标项目目录**、升级前代码路径和升级后工作区；实际修改只允许落在目标项目或该目标项目明确依赖的通用指纹模块中。
- `TRAN_TARGET_DEVICE`、产品名、继承模板、参考文档中的项目名只可作为线索；不得据此直接修改其它项目专属目录（例如用户要求 LJ8 时，不应改 X6870 项目目录）。
- 若目标项目与复用机型/基线项目命名不一致，先向用户确认应新增目标项目配置、复用既有配置，还是等待补充升级前代码；确认前只做只读核对和风险记录。

## 编写规划

1. **先分类**：升级前后指纹架构（归一化 / 非归一化）须一致；以**升级前** `kernel/.../drivers/input/fingerprint` 下 `tran_common` 或 `tran_common_v2` 及 `tran_fp_main.c` 的 **compatible** 为主判定，HAL/Log 仅作参考。
2. **定参考**：架构判定后立即选择参考扩展：**非归一化**优先参考 [EXTENSION_CM5.md](EXTENSION_CM5.md)、[EXTENSION_X6885.md](EXTENSION_X6885.md)；**归一化**优先参考 [EXTENSION_NORMALIZED_SUNMAO.md](EXTENSION_NORMALIZED_SUNMAO.md)。扩展只作为同架构参考，不可越过用户指定项目边界。
3. **再按序**：驱动 → DTS → DWS（三处）→ 工模与 `Sensor.json` → `vendor/transsion/projects` 下 KO、`device-vext.mk`、指纹库目录与厂商客制、`tran_core.c`。
4. **强约束**：只有 **DTS 与 DWS** 需要严格按照升级前目标项目信息逐项对齐；`ProjectConfig.mk`、`device-vext.mk`、`fp_fw`、TA/库等须以主 SOP 明确项、同架构参考项目和用户补充材料为依据，依据不足时暂停询问。
5. **后验证**：编译刷机，按需抓 log；异常可走日志分析 Skill。
6. **长片段**：DTS 大块与 JSON 模板见 [REFERENCE.md](REFERENCE.md)（与主 Wiki 二、章一致摘录）。
7. **参考资料**：主文档**第三节**中的三篇典型项目飞书及 [EXTENSION_CM5.md](EXTENSION_CM5.md)、[EXTENSION_X6885.md](EXTENSION_X6885.md)、[EXTENSION_NORMALIZED_SUNMAO.md](EXTENSION_NORMALIZED_SUNMAO.md) 作**参考**；需要与 CM5 / X6885 / 归一化榫卯等案例对照、或需编译脚本与 Gerrit 等细节时再打开。**日常步骤仍以主文档一、二章及本 SKILL 上文为准**。

---

## 一、升级项目指纹 P1 调试基础信息

### 1. 什么是升级项目？

- 当前 Android 版本为 **Android 15**，目标升级到 **Android 16**。
- 升级分 system 与 **vendor**；指纹模块主要关注 **vendor**。
- 不同项目升级前 vendor / kernel 不同，例如 **CM5、X6885**：升级前 vendor **12**、kernel **5.10**，升级后 vendor **16**、kernel **6.12**；**X6876、CM8、X6857** 等：升级前后 vendor **14**、kernel **6.1** 不变。
- 升级项目从旧代码分支迁移到**榫卯**新分支适配。

### 2. 升级项目指纹需要调试什么？

- 指纹**驱动**
- 指纹 **DTS**
- 指纹 **DWS**
- 指纹 **CA / TA** 库配置
- 指纹**工模**配置

---

## 二、升级项目指纹调试步骤

### 1. 明确升级前指纹代码架构（归一化 / 非归一化）

**原则**：升级前非归一化 → 升级后仍非归一化；升级前归一化 → 升级后仍归一化。

经验提示（非绝对）：升级前 vendor **12** 多为非归一化，vendor **14** 多为归一化；**须按具体项目判断**。

**主判定（以此为准）**

在升级前分支查看：`kernel/kernel_device_modules-<ver>/drivers/input/fingerprint/`（版本号随项目调整）。

| 条件 | 结论 |
|------|------|
| 仅有 `tran_common`，且 `tran_common/tran_fp_main.c` 中 `.compatible = "tran_fp"` | **非归一化** |
| 仅有 `tran_common_v2`，且 `tran_common_v2/tran_fp_main.c` 中 `.compatible = "tran_fp"` | **归一化** |
| **两套驱动同时存在** | **暂停**：警示用户，待确认后再继续 |

**辅助参考（不可单独作为唯一依据）**

- 服务：`android.hardware.biometrics.fingerprint-service`（AIDL）多为归一化；`android.hardware.biometrics.fingerprint@2.1-service`（HIDL）多为非归一化。
- Log：tag **`tran_hal`** 多为归一化；**`xxx_hal`**（供应商名）多为非归一化。

非归一化与归一化升级调试路径不同，须**严格按已判定架构**执行。

**架构判定后的参考选择**

- 判定为**非归一化**：打开 [EXTENSION_CM5.md](EXTENSION_CM5.md)、[EXTENSION_X6885.md](EXTENSION_X6885.md)，只参考同类路径、库目录、`device-vext.mk` 结构和提交经验。
- 判定为**归一化**：打开 [EXTENSION_NORMALIZED_SUNMAO.md](EXTENSION_NORMALIZED_SUNMAO.md)，重点参考归一化榫卯路径、`tran_common_v2`、`fp_fw`、ODM TA 和工模配置。
- 扩展文档中的项目名只能作为参考案例名；实际修改仍只落在用户指定目标项目和其明确依赖的通用指纹模块。

### 2. 驱动适配调试

在**升级后**分支检查驱动是否已适配。

**非归一化**

- 路径示例：`kernel/kernel_device_modules-6.12/drivers/input/fingerprint/`（以实际为准）。
- 存在 `tran_common`；若 `tran_fp_main.c` 中 **`.compatible = "tran_fp"`**，须改为 **`.compatible = "tran_fp_legacy"`**（与 DTS 一致）。

**归一化**

- 路径示例：`kernel/kernel_device_modules-6.1/drivers/input/fingerprint/`。
- 存在 `tran_common_v2`；`tran_fp_main.c` 保持 **`.compatible = "tran_fp"`**。

### 3. DTS 配置

**依据升级前**工程做升级后适配。

- **非归一化**：升级后 `fingerprint` 节点 **`compatible = "tran_fp_legacy"`**；对照升级前节点与 pinctrl；文档示例路径含 `x6885_h8923.dts`（kernel-5.10 → kernel_device_modules-6.12）。完整节点与 `&pio` 见 [REFERENCE.md](REFERENCE.md)。
- **归一化**：升级前后 **`compatible = "tran_fp"`**；文档示例 `x6876_h786.dts`（`kernel_device_modules-6.1`）。详见 [REFERENCE.md](REFERENCE.md)。

**DTS 必查清单**

- 逐项对齐升级前目标项目 `fingerprint@*` 节点：`compatible`、`reg`、`spi-max-frequency`、`interrupt-parent`、`interrupts`、`debounce`、`irq-gpio`、`reset-gpio`、电源 supply / power GPIO、`fod_location_xy`、`pinctrl-names`、`pinctrl-*`、`status`。
- 逐项对齐 `fingerprint` 节点引用到的 `&pio` pinctrl：IRQ、reset、power、SPI 相关 pinmux / pull / output 状态。只对齐这些被指纹节点引用的 label，不按全文件差异修改其它外设。
- DTS 是 DWS 的依据之一：后续 DWS 只允许修改 DTS 指纹节点实际使用的 GPIO / SPI / power 引脚，禁止改与指纹无关的 LCM、I2C、NFC、TP、sensor 等引脚。

### 4. DWS 配置

按升级前配置 **SPI / 中断 / 复位**；若 GPIO 供电则加 **power**；共**三处** DWS 须一致。

**DWS 修改原则**

- 先从升级前 / 升级后 DTS 的 `fingerprint` 节点提取实际用到的 GPIO 与 SPI：`irq-gpio`、`reset-gpio`、power GPIO / supply、`pinctrl-*` 指向的 SPI pins。
- 只在三处 DWS 中对齐这些指纹相关引脚；不要因为全文件 diff 或相邻引脚差异去修改与指纹无关的引脚。
- SPI 相关引脚必须重点核对：若 DTS 中存在 `tran_fp_spi_default` / `fingerprint_spi_default` 等 pinctrl，需追踪其 pinmux 到 DWS 中对应 SPI 引脚，并与升级前一致。
- DWS 三处都要核对：Preloader、Kernel DCT、Tools DWS；输出结果时分别说明已对齐项和未对齐原因。

**非归一化**（文档示例 **x6885_h8923 / mt6789**）

| 阶段 | 升级前参考路径（示例） | 升级后路径（示例） |
|------|------------------------|---------------------|
| Preloader | `.../preloader/custom/x6885_h8923/dct/dct/codegen.dws` | `vendor/mediatek/.../preloader/custom/x6885_h8923/dct/dct/codegen.dws` |
| Kernel DCT | `.../custom/x6885_h8923/kernel/dct/dct/codegen.dws` | `vendor/mediatek/.../custom/x6885_h8923/kernel/dct/dct/codegen.dws` |
| Tools | `.../tools/dct/dws/mt6789/x6885_h8923.dws` | `vendor/mediatek/.../tools/dct/dws/mt6789/x6885_h8923.dws` |

**归一化**（文档示例 **x6876_h786 / mt6878**）

| 阶段 | 升级前参考路径（示例） | 升级后路径（示例） |
|------|------------------------|---------------------|
| Preloader | `.../preloader/custom/x6876_h786/dct/dct/codegen.dws` | `vendor/mediatek/.../preloader/custom/x6876_h786/dct/dct/codegen.dws` |
| Kernel DCT | `.../custom/x6876_h786/kernel/dct/dct/codegen.dws` | 同上 pattern |
| Tools | `.../tools/dct/dws/mt6878/x6876_h786.dws` | `vendor/mediatek/.../tools/dct/dws/mt6878/x6876_h786.dws` |

实际项目名、芯片目录须替换为当前工程。

### 5. 工模配置

**非归一化**

- 检查升级后是否有对应指纹厂商**工模 APK**：参考路径 **`/vendor/transsion/system_modules/common/fingerprint/`**；若无，**提示用户**，不得虚构 APK。
- 按光学/电容配置 **`Sensor.json`**；文档示例路径：  
  `/vendor/transsion/vendor_modules/tranfac/TranfacVnd/config/project/mtk/X6885/feature/Sensor.json`（项目名替换）。非归一化光学 JSON 示例见 [REFERENCE.md](REFERENCE.md)。

**归一化**

- 路径示例：`/vendor/transsion/vendor_modules/TranfacVnd/config/project/mtk/X6876/feature/Sensor.json`。
- **光学**：`tranfac.sensor.fingerprint.optical` + `tranfac.sensor.fingerprint.tran_common_tee`。
- **电容**：仅 `tranfac.sensor.fingerprint.tran_common_tee`。  
  完整示例见 [REFERENCE.md](REFERENCE.md)。

### 6. 指纹库配置

因项目客制差异大，框架相同，须按**指纹 IC** 取库。

**`device-vext.mk` 参考项目规则**

- 只有在用户明确给出**可参考项目**后，才按参考项目迁移 `device-vext.mk` 中指纹库 / TA 拷贝结构；不得在 Skill 中固定某个参考项目。
- 迁移前必须先读取目标项目与参考项目的 `device-vext.mk`，对照 `TRAN_FP_PROJECT_INFO`、`TRAN_FP_DISPLAY_INFO`、`fp_fw` 拷贝、权限与 manifest、`fp/ta`、`mcRegistry`、tabin / drbin 等结构。
- 配置 TA 拷贝时必须区分 **debug / release**，按参考项目中实际分支与产物路径迁移到目标项目；若目标项目暂无 TA 产物，可先搭建目录或注释态结构，并标记“待生成 / 待确认”，不得当作完成项。
- 若用户未给出参考项目，且仓库中无法可靠确定同架构 / 同 IC 项目，应暂停并询问用户；在询问前只做只读核对或占位结构搭建。

**非归一化**

1. 先确认 **`/vendor/transsion/projects`** 下其它配置正确。
2. **`ko_order_table.csv`**：配置 **`tran_fp.ko`**（文档示例：`.../kernel_device_modules-6.12/drivers/input/fingerprint/tran_fp.ko`，分区 **ramdisk** 等列见主 Wiki）。
3. **`ProjectConfig.mk`**：只处理主 SOP 明确要求项；非归一化**不应**误加归一化工模宏。不要凭升级前项目配置主动新增未在主 SOP 说明的宏。
4. 升级后 TA 从 **ODM** 加载，一般**不能**完全复用升级前 CA，需供应商提供 **CA + TA**。
5. **`device-vext.mk`**：按主 Wiki示例和用户指定参考项目配置 `PRODUCT_COPY_FILES`、`PRODUCT_PACKAGES`、debug/release **tabin** 等（供应商与 SPI 目录随项目变）；不得默认指定某个参考项目。
6. 目录 **`vendor/transsion/projects/<project>/fp/`**：存放 TA、CA、rc、vintf 等；若无则创建。

**归一化**

1. 先确认 **`/vendor/transsion/projects`** 下其它配置正确。
2. **`ko_order_table.csv`**：配置 **`tran_fp_v2.ko`**（文档示例指向 `tran_common_v2`，分区 **odm** 等列见主 Wiki）。
3. **`ProjectConfig.mk`**：只关注主 SOP 明确说明的内容，不要主动新增未在文档中要求的项目宏或坐标属性，例如 `TRAN_FINGERPRINT_PROJECT`、厂商型号拼接的 `TRAN_FINGERPRINT_SUPPORT`、`TRAN_TEE_ARM`、`MTK_TEE_SPI*_64`、`vendor.tran.fp.center.*.offset` 等；若构建报缺宏，再结合参考项目或用户确认处理。
4. **算法库**：升级前后与**量产**一致；必须在升级前代码的 `/vendor/transsion/bsp/fingerprint/transsion/ta/` 下定位目标项目 / 目标 IC 的 **`libtran_vnd.a`** 等库。定位时不要只按文件名全局搜索，先读取升级前 `tee_config.mk`，确认目标 IC 实际参与编译的 `makefile.mk`；再读取该 IC `makefile.mk`，检查 `STD_LIBS`、`$(TARGET_MODE)`、debug/release、optics/capacitive/side、项目名 `ifeq` / `findstring` 等差异分支，确定应取哪一份 `.a` 库。拷贝到升级后时也要先读取升级后 `tee_config.mk` 和对应 IC `makefile.mk`，以其实际引用路径决定目标目录；目标根目录通常为 `vendor/transsion/vendor_modules/fingerprint/transsion/ta/<厂商>/libs/`，具体子路径以升级后构建入口和 IC makefile 为准。若 `tee_config.mk` 与 IC makefile 指向不同 TA 结构（例如厂商公共 makefile 与具体 IC makefile 并存），以实际被 `TEE_ALL_MODULE_MAKEFILE` 引入的具体 IC makefile 为优先；无法唯一判断时暂停询问用户。
5. **`device-vext.mk`**：文档示例含 `TRAN_FP_PROJECT_INFO`、`TRAN_FP_DISPLAY_INFO`、`fp_fw` 拷贝、权限与 manifest、**tabin/drbin** 的 debug/release；实际迁移时以用户指定参考项目的 `device-vext.mk` 为准，不在 Skill 中固定参考项目。
6. 若用户没有提供可参考的指纹库配置项目，且仓库中无法确定同 IC/同架构项目，应**暂停调试并询问用户参考项目**。可先搭建 `fp/`、`fp_fw/`、`device-vext.mk` 的代码结构，但必须标注“待用户确认/待替换”，不得把占位内容当作完成项。
7. **`fp/`**：存放 TA；**`fp_fw/`**：项目信息 json 等（主 Wiki 示例路径请按仓库核对）。
8. **`fp_fw/tran_fp_project_info.json`**：可按项目名、vendor、display IC、offset、ODM TA 加载字段更新；若无法确定 checksum 生成工具或算法，**不要修改原 checksum 或仅在新增草稿文件中置 0**，并在输出中明确提示后续需生成/修正 checksum。
9. **display JSON**（如 `tran_fp_<project>_<IC>_<module>_<display>.json`）：没有同 IC/同项目参考配置时不要编造算法参数；可创建占位结构用于编译路径验证，但输出必须标记为“未填充，等待参考项目/供应商配置”。
10. **Goodix 等厂商客制配置**：先查看**升级前目标 IC** 的 TA makefile / 源码是否实际引用或需要 `gf_config_ex.c` / `gf_config_ex.h` 等厂商配置文件，并确认这些文件与目标项目的关系；只有升级前目标 IC 确实使用这类配置时，才继续检查升级后对应 IC 构建链是否已有等价文件或项目宏，决定是否移植到升级后代码。若升级前目标 IC 不使用这类配置文件，或对应厂商不是 Goodix，应按实际厂商 makefile / 配置文件处理，不要机械移植 Goodix 文件。
11. **`tran_core.c`**：先确认升级后目标 IC 实际编译的 TA 源码是否使用 `vendor/transsion/vendor_modules/fingerprint/transsion/ta/tran_common/tran/tran_core.c`，并检查其中是否存在 `tran_extra_cmd(E_SET_CONFIG, ...)` 代码块；只有主 SOP / 同架构参考项目要求且目标构建链实际命中该文件时，才注释该代码块（原文见 [REFERENCE.md](REFERENCE.md)）。若目标 IC 使用厂商独立 `tran_core.c` 或代码块已不存在，不要无条件修改公共 `tran_core.c`，需在输出中说明判定依据。

---

## 三、参考信息（主文档第三节）

主文档第三节列出典型场景及三篇**参考**飞书；本 SKILL **一、二章**已覆盖主流程，下表便于按项目打开参考链接与仓库摘录。

| 场景（主文档归纳） | 典型项目 | 参考飞书 | 仓库参考摘录 |
|--------------------|----------|----------|----------------|
| vendor12 → vendor16，升级前**非归一化** | CM5、X6885 | [CM5 升级调试](https://transsioner.feishu.cn/wiki/RQjRw7YfjiXUOUkaTjIc9c6onSg)、[X6885 指纹开发记录](https://transsioner.feishu.cn/wiki/G2p1wEUC5iERW7kqhpMcyPkfnxd) | [EXTENSION_CM5.md](EXTENSION_CM5.md)、[EXTENSION_X6885.md](EXTENSION_X6885.md) |
| vendor14 非榫卯 → vendor14 **榫卯**，升级前**归一化** | X6876、CM8、X6857 | [归一化项目升级榫卯指纹调试](https://transsioner.feishu.cn/wiki/DXGIwLBtqiitppkWO90cx6k3nZf) | [EXTENSION_NORMALIZED_SUNMAO.md](EXTENSION_NORMALIZED_SUNMAO.md) |

**主文档（主要调试依据）**：[升级项目指纹调试 / AI 辅助指纹 P1 调试](https://transsioner.feishu.cn/wiki/A74wwMGsLiTCBXkMJjVccUDfnKd)

### Agent 使用参考文档的方式

- **主要**：按**主文档**与本 SKILL **一、二章**、[REFERENCE.md](REFERENCE.md) 执行指纹 P1 调试。
- **参考**：完成架构判定后立即选择同架构扩展：非归一化看 CM5/X6885，归一化看归一化榫卯；**MCP 可用**时对子 Wiki `convert_feishu_wiki_to_document_id` 后 `get_feishu_document_raw_content`。
- **MCP 不可用**：可请用户提供参考文档要点；不得编造参考材料中的路径或命令。

---

## 与日志分析 Skill 的配合

- **本 Skill**：以**主文档**流程与配置核对为主；必要时对照**参考**文档与 EXTENSION。
- **`android-fingerprint-log-analysis`**：`tran_fp`、`tran_hal`、`android.hardware.biometrics.fingerprint`、`chip_id`、`spmt`、`uuid`、`tabin` 等 log 验证。

---

## 指纹 P1 适配进度（清单）

```
指纹 P1 适配进度（主 Wiki 二、章）：
- [ ] 1. 架构判定（归一化/非归一化）；两套驱动并存则暂停待用户确认
- [ ] 2. 同架构扩展参考选择（非归一化 CM5/X6885；归一化 NORMALIZED_SUNMAO）
- [ ] 3. 驱动 compatible（tran_fp vs tran_fp_legacy）
- [ ] 4. DTS（严格对照升级前 fingerprint 节点与 pinctrl）
- [ ] 5. DWS 三处（只对齐 DTS 指纹节点实际使用的 IRQ/reset/power/SPI 引脚）
- [ ] 6. 工模 APK + Sensor.json（光学/电容按架构）
- [ ] 7. ko_order_table、ProjectConfig（只做主 SOP 明确项）、device-vext.mk（按用户指定参考项目区分 debug/release）、fp/、fp_fw、厂商库（先查 tee_config 与 IC makefile）与 tran_core.c 注释
- [ ] 8. 若缺参考项目/库/checksum/display JSON 参数，暂停并列为待用户确认
```

---

## 输出建议（适配记录）

```markdown
## 指纹 P1 适配记录 — <项目代号>

- **架构**：归一化 / 非归一化（判定依据：驱动路径与 compatible）
- **参考扩展**：已按架构查阅的 EXTENSION / 飞书
- **驱动**：修改文件与 compatible 最终值；未修改则说明原因
- **DTS**：已对齐的 fingerprint 节点、pinctrl、仍有差异项
- **DWS**：Preloader / Kernel DCT / Tools 三处分别列出 IRQ、reset、power、SPI 对齐情况；说明未动的无关引脚
- **工模**：APK 是否存在；Sensor.json 路径与 feature
- **构建配置**：ko_order_table、ProjectConfig、device-vext.mk；ProjectConfig 只列主 SOP 明确项；device-vext 说明参考项目、debug/release 分支与 TA 拷贝结构
- **库/TA/fp_fw**：升级前 `tee_config.mk` 与 IC `makefile.mk` 判定结果、`libtran_vnd.a` 等库查找与拷贝结果；ODM tabin/drbin 的 debug/release 产物；project_info checksum 是否已生成；display JSON 是否有真实参数
- **已完成**：按上述步骤顺序列清楚
- **阻塞未完成**：缺库、缺参考项目、缺 checksum 工具、缺 display JSON 参数等
- **需要用户确认**：参考项目、供应商库、checksum 生成方式、占位文件是否可接受
```
