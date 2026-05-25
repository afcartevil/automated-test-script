# 阶段 2：MTK_CODE/quark/kernel_device_modules-6.1 (或 6.12) DTS

**目标 repo**：`MTK_CODE/quark/kernel_device_modules-6.1`（vnd14 → vnd14）或 `MTK_CODE/quark/kernel_device_modules-6.12`（vnd12 → vnd16）

**目标文件**（本阶段 **只修改** 升级后项目 DTS）：

- `post_project_dts_path` = `{base_code_sunmao}/kernel/kernel_device_modules-<ver>/arch/arm64/boot/dts/mediatek/{project_name_sunmao}.dts`

**只读、不修改**：

- 升级前取值源：`pre_project_dts_path`（§5.2，项目 DTS）
- 升级前平台 DTS `pre_platform_dts_path`（§5.3）**不在本阶段读取**——ADSP 检测已在阶段 1 完成；禁止用平台 DTS 抄 PA/GPIO 取值。

数据源：[references/dts-node-templates.md](../references/dts-node-templates.md)、[references/variables.md §5~§6](../references/variables.md)。

## 阶段门禁（严格 SOP）

- 本阶段只能在阶段 1 checkpoint 得到开发者明确放行后执行。
- 本阶段未完成 checkpoint 前，禁止提前改写阶段 3/4/5 的 DWS 或其他后续文件。
- 本阶段若出现父节点不一致（如升级前挂 `&i2c10`、升级后写入 `&i2c3`），必须停下提问，不得继续推进。

## 一、勘察

1. Read 升级前项目 DTS（**`pre_project_dts_path`**，按 [variables.md §5.2](../references/variables.md) 在 `tran_projects_root` 下解析；禁止读仓库根 `{base_code}/kernel/.../{project_name_sunmao}.dts`）：
   - Grep 当前 PA 类型对应节点名（`aw87xxx_pa` / `oca72xxx_pa` / `fs15xx_pa`）。
   - Grep `tran_audio_controller`。
   - Grep `hl1280` / `dio1520` 判定 typec switch 类型。
   - Grep `typec_usb_change_gpio` / `audio_usb_switch_dio32020` / `mic_gnd_switch_dio1520` 取 GPIO **引脚编号**（仅取值，不抄节点格式）。
2. Read 升级后项目 DTS（目标文件）与 [dts-node-templates.md §0](../references/dts-node-templates.md)：**格式以升级后模板为准**。

## 二、执行步骤

### 2.0 升级后 DTS 中既有音频节点的全量清理（动手移植前先做）

在执行 §2.1~§2.3 之前，必须先把升级后项目 DTS 中 **本 SOP 涉及的全部音频节点** 整段删除，给后续移植留出干净的注入位。涉及节点（任一存在则删整段，包括节点头、属性与花括号闭合）：

- 4 个 PA 节点（全部，不只删当前 PA 类型）：
  - `aw87xxx_pa`
  - `oca72xxx_pa`
  - `fs15xx_pa`
- `tran_audio_controller`（含 `tran_audio_controller:tran_audio_controller { ... };` 整段）。
- 全部 typec switch 节点（无论当前类型）：
  - `hl1280-audioswitch`
  - `tran_audio_sliptswitch`
  - `tran_audio_sliptswitch_gpio`
- 升级前解耦遗留、模板外节点（存在则删）：
  - `tran_audio`（`compatible = "tran_audio,audio"`）

操作要点：

- 用 Grep 在升级后项目 DTS 中按节点名定位起点；用 Read 取上下文确认花括号闭合 + 末尾分号 `;` 的真实终点，再用 StrReplace 把整段删除。
- 节点位于 `&i2cX { ... };` / `&odm { ... };` 这类父引用块下时，仅删 **该子节点**，不要把父引用块一起删掉。
- 删除完成后 Grep 上述节点名应 **全部 0 命中**；若仍命中说明残留，必须回查。
- 删除范围 **不要扩大**：本步骤只删上面 6 个节点名；DTS 中其他与 SOP 无关的节点一律不动。

> 这一步是 §1.2 PA 旧目录"全删后重建"理念在 DTS 侧的对等动作：先清干净再注入，避免与升级后 DTS 残留节点合并时的歧义。

### 2.1 PA 节点

按 [dts-node-templates.md §1](../references/dts-node-templates.md)：

- 在升级前 DTS 中 Grep 当前 PA 节点，**仅记录** I2C 总线号、`reg`、`dev_index` 等取值。
- 在升级后 DTS 对应 `&i2cX` 下按 [dts-node-templates.md §1](../references/dts-node-templates.md) **模板结构**追加 PA 子节点并填入上述取值；**禁止**复制升级前整段节点格式。
- 升级前后 I2C 总线编号不一致 → 跳出，问开发者。
- checkpoint 中必须记录："PA 节点升级前父节点"、"PA 节点升级后父节点"、"是否一致(yes/no)"。

### 2.2 `tran_audio_controller` 节点

按 [dts-node-templates.md §2](../references/dts-node-templates.md)：

1. 在 `&odm { ... };` 块内 **追加** 节点（§2.0 已把旧节点删除，不需要再做"已存在 → 替换"）。
2. `tran_pa_type` 取值：按 §2.1（数值表 AW=3 / FS1599N=2 / FS1589N=5 / OCA=4）。
3. `tran_typec_type` 取值：按 §2.2（HL1280=2 / DIO1520=3 / 3.5mm 省略）。
4. 三个 GPIO 属性：按 §2.3 从升级前 DTS **仅取引脚号**，写在 `tran_audio_controller` 上（禁止写在 `tran_audio` / `tran_audio_sliptswitch_gpio` 等模板外节点）。

### 2.3 typec switch 节点

按 [dts-node-templates.md §3](../references/dts-node-templates.md) **升级后模板**追加（禁止抄写升级前节点格式）：

- HL1280：在正确 `&i2cX` 下按 §3.1 模板追加；`reg`/总线号取自升级前。
- DIO1520：§2.2 已写 `tran_audio_controller`（含 `tran_typec_type=<3>` 与三件套 GPIO）后，在 `&odm` 下按 §3.2 追加两个 **仅 compatible** 的 sliptswitch 节点；**不得**追加 `tran_audio`。
- 3.5mm：跳过本步。
- checkpoint 中必须记录："HL1280 或 DIO1520 节点的升级前父节点/升级后父节点/一致性"。

## 三、自检（按 [dts-node-templates.md §4](../references/dts-node-templates.md)）

- 节点清理：§2.0 列出的 6 个节点名在升级后 DTS 中 0 命中（除当前 PA 类型对应的 1 个节点和 typec switch 对应的节点是在 §2.1~§2.3 重新追加的）。
- PA 节点：已移植、I2C 总线编号与升级前一致；且 4 个 PA 节点名中只有当前 PA 类型对应的 1 个存在。
- `tran_audio_controller`：在 `&odm` 下、三个 enum/类型属性自洽、GPIO 属性齐全或合理省略。
- typec switch 节点：HL1280 挂正确 I2C / DIO1520 两节点齐全 / 3.5mm 全部 0 命中。
- 升级前后 GPIO 号一致。
- 父节点一致：PA/typec 相关节点在升级前后 DTS 的父节点逐项一致。
- 升级后 DTS 仅含模板允许的节点名；Grep `tran_audio` 为 0；DIO1520 时 `tran_audio_sliptswitch_gpio` 内无 GPIO 属性。

## 四、阶段 2 Checkpoint

| 项 | 内容 |
| --- | --- |
| 本阶段改了什么 | 列出升级后项目 DTS 中新增/替换的节点（PA / tran_audio_controller / typec switch）；列出每个 GPIO 编号取值；列出 `tran_pa_type` / `tran_typec_type` 取值 |
| 还差什么 | I2C 总线冲突 / GPIO 升级前缺失 / typec 类型双命中或异常 / 升级后 DTS 已存在的冲突节点未能合并 / 平台 DTS 中 `mtk-dsp-type` 异常（前一阶段已发现） |
| 是否继续 | 默认询问"是否进入阶段 3（preloader DWS）？" |

## 五、跳出条款

- §2.0 清理时发现升级后 DTS 中存在 SOP 列表外的 **额外** 音频相关自定义节点（例如某项目曾在 `&odm` 下加过 `tran_audio_xxx_extra` 等非 SOP 名节点）→ 跳出，不要顺手删；问开发者是否需要保留。
- §2.0 清理时 6 个节点名 Grep 命中位置嵌套异常（如节点头与花括号闭合不在一个父引用块内）→ 跳出，问开发者；不要尝试自动修复 DTS 语法。
- `pre_project_dts_path` 中找不到当前 PA 类型对应的节点（升级前项目使用了完全不同的 PA 类型）→ 跳出，问开发者是否本次升级伴随 PA 切换。
- I2C 总线编号在升级前后 DTS 中不一致（如升级前 `&i2c3`、升级后平台 BSP 改为 `&i2c5`）→ 不要硬抄升级前总线号，问开发者新总线号。
