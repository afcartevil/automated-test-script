# 变更记录

本文档记录 `DRV_FP_Adapt` 的重要版本变更。

## [1.1.6] - 2026-05-14

### 修正

- 修正厂商客制配置判断顺序：应先检查升级前目标 IC 的 TA makefile / 源码是否实际引用或需要 `gf_config_ex.c` / `gf_config_ex.h` 等配置，再决定升级后是否需要承接移植，避免先从升级后路径倒推导致机械套用 Goodix 逻辑。

## [1.1.5] - 2026-05-14

### 改进

- 调整 `gf_config_ex.c` / `gf_config_ex.h` 处理策略：先检查升级后目标 IC 的 TA makefile 和源码是否实际引用或需要这些厂商配置文件，再决定是否从升级前移植，避免机械套用 Goodix 路径到其它厂商。
- 调整 `tran_core.c` 处理策略：先确认目标 IC 实际编译链命中的 `tran_core.c` 以及是否存在 `tran_extra_cmd(E_SET_CONFIG, ...)` 代码块，再决定是否按主 SOP / 参考项目注释，避免无条件修改公共文件。

## [1.1.4] - 2026-05-14

### 改进

- 优化 `.a` 算法库定位流程：升级前先读取 `tee_config.mk` 确认目标 IC 实际参与编译的 `makefile.mk`，再根据该 makefile 中的 `STD_LIBS`、`$(TARGET_MODE)`、debug/release、指纹类型和项目差异分支确定应取哪一份 `libtran_vnd.a`。
- 明确拷贝到升级后时也需读取升级后 `tee_config.mk` 与对应 IC `makefile.mk`，以实际构建入口和 IC makefile 的引用路径决定目标目录。
- 补充厂商公共 makefile 与具体 IC makefile 并存时的优先级：以 `TEE_ALL_MODULE_MAKEFILE` 实际引入的具体 IC makefile 为优先，无法唯一判断时暂停询问用户。

## [1.1.3] - 2026-05-13

### 改进

- 增加 `device-vext.mk` 参考项目规则：只有在用户明确提供参考项目后，才按参考项目迁移指纹库 / TA 拷贝结构，不在 Skill 中固定某个参考项目。
- 强化 `device-vext.mk` 的 debug / release 区分要求：迁移 TA、tabin / drbin、`mcRegistry` 等配置时必须分别核对参考项目的 debug 与 release 分支。
- 明确缺少参考项目或 TA 产物时，只能搭建目录或注释态占位结构，并在输出中标记为待生成 / 待确认。

## [1.1.2] - 2026-05-13

### 修正

- 明确算法库拷贝到升级后的目标目录：以 `vendor/transsion/vendor_modules/fingerprint/transsion/ta/<厂商>/libs/` 为目标根目录，并以升级后对应厂商 TA `makefile.mk` 中 `STD_LIBS` 引用的子路径为准。

## [1.1.1] - 2026-05-13

### 修正

- 修正算法库搜索路径：升级前 `libtran_vnd.a` 等库应在 `/vendor/transsion/bsp/fingerprint/transsion/ta/` 固定根目录下搜索，差异只体现在其后的厂商、平台、指纹类型、debug/release、项目等子目录。

## [1.1.0] - 2026-05-13

### 改进

- 架构判定后立即选择同架构扩展文档：非归一化参考 CM5 / X6885，归一化参考归一化榫卯调试。
- 强化 DTS / DWS 规则：DTS 必须逐项对齐升级前目标项目；DWS 只允许修改 DTS 指纹节点实际使用的 IRQ、reset、power、SPI 引脚，不修改无关外设引脚。
- 收紧 `ProjectConfig.mk` 处理范围：只处理主 SOP 明确项，不主动新增未在文档要求的项目宏、TEE SPI 宏或坐标属性。
- 调整 `device-vext.mk`、`fp_fw`、TA / 库处理策略：缺少参考项目、缺少库、无法确定 checksum 或 display JSON 参数时暂停并询问用户。
- 增加升级前 `libtran_vnd.a` 搜索要求。
- 优化最终输出模板，要求按调试步骤顺序列出已完成项、阻塞未完成项和需要用户确认项。

## [1.0.1] - 2026-05-13

### 修正

- 补充项目落地边界：执行指纹调试时必须以用户指定的目标项目和升级前代码为准。
- 明确 `TRAN_TARGET_DEVICE`、复用机型名、模板项目名和参考案例名只能作为线索，不能直接作为修改其它项目目录的依据。
- 强调目标项目与基线项目命名不一致时，需先确认或等待补充升级前代码，再做落地修改。

## [1.0.0] - 2026-05-13

### 新增

- 创建 `DRV_FP_Adapt` 初始正式版，用于 Transsion/MTK vendor 侧指纹 P1 适配。
- 基于主 SOP 增加主要调试流程：
  - 归一化 / 非归一化架构判定。
  - 驱动 compatible 适配。
  - DTS 与 DWS 适配。
  - 工模与 `Sensor.json` 配置。
  - KO、项目宏、`device-vext.mk`、CA/TA、指纹库检查。
- 新增 `REFERENCE.md`，用于存放主 SOP 中较长的示例和片段。
- 新增参考扩展文档：
  - `EXTENSION_CM5.md`
  - `EXTENSION_X6885.md`
  - `EXTENSION_NORMALIZED_SUNMAO.md`
- 新增版本管理文件：
  - `VERSION.md`
  - `CHANGELOG.md`

### 说明

- 本版本为正式版：主流程以主 SOP 作为主要调试依据，三个 `EXTENSION_*.md` 文件作为参考材料。
