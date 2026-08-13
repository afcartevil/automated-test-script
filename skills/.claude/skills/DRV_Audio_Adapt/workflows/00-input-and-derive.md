# 阶段 0：输入采集 + 变量推导

**目标**：把开发者的输入凝结成一张「变量确认表」，确认无歧义后再开始改文件。本阶段 **只读**，不写任何文件，无论 SKILL 处于 `execute_phased` 还是 `audit_only` 模式。

## 一、检查输入完整性

按 [SKILL.md §输入契约](../SKILL.md) 的 5 项，逐项核对：

| 必需项 | 检查方式 |
| --- | --- |
| `base_code` | 路径存在？目录下是否有 `tran_projects/` |
| `base_code_sunmao` | 路径存在？目录下是否有 `vendor/transsion/projects/` |
| `scenario` | 取值是 `vnd12_to_vnd16` 或 `vnd14_to_vnd14` 二选一 |
| `project_compile_option` | 是字符串或图片；图片需要清晰可读 |
| `sw_config_table` | 是图片或文本；关键字段（PA 型号 / SPK 个数 / SPK PATH / MIC 个数 / `PHONE_MIC_MODE` / `HEADSET_MIC_MODE` / TypeC 耳机字段）是否齐全 |

任一项缺失或不清晰 → **立即停下询问开发者**，不要进入二步推导。

## 二、变量推导（按 [references/variables.md](../references/variables.md) §2~§5 顺序）

### 2.1 切分 `project_name`

把 `project_compile_option` 按 `_` 切分，依次得到 `project_name1` / `project_name2` / `project_name3` / ...，并保留全名 `project_name`。

### 2.2 找 `project_name_sunmao`

在 `{base_code_sunmao}/vendor/transsion/projects/` 下列子目录，按 [variables.md §3](../references/variables.md) 的"精确 > 前缀 > 包含"策略选定。命中多项或 0 项 → 必须问开发者。

### 2.3 取 `platform_name`

读取 `{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/ProjectConfig.mk`，找 `MTK_PLATFORM = <value>`，把 `<value>` 转小写 → `platform_name`。读不到则到同目录其他 `ProjectConfig*.mk` 里再找一次；仍无 → 问开发者。

### 2.4 找 `kernel_old`

在 `tran_projects_root`（见 [variables.md §5.0](../references/variables.md)）下，列**直接子目录**，取以 `kernel` 开头的目录名作为 `kernel_old`。

- **只取第一层**目录名（如 `kernel`），不要把内层 `kernel_device_modules-6.1` 误当成 `kernel_old`。
- 命中多个或 0 个 → 跳出、问开发者。

### 2.5 解析 `pre_project_dts_path`（升级前 **项目** DTS）

按 [variables.md §5.2](../references/variables.md) 顺序执行（**仅** `tran_projects_root`，文件名 `{project_name_sunmao}.dts`）：

1. 拼模板 `{tran_projects_root}/{kernel_old}/arch/arm64/boot/dts/mediatek/{project_name_sunmao}.dts`，存在则采纳。
2. **模板不存在** → 在 `tran_projects_root` 下 Glob `**/arch/arm64/boot/dts/mediatek/{project_name_sunmao}.dts`。
3. Glob 命中 1 个 → 写入变量确认表；命中多个 / 0 个 → 问开发者。
4. **禁止**使用 `{base_code}/kernel/**/{project_name_sunmao}.dts` 作为升级前项目 DTS。

示例（lj7）：

```
tran_projects/lj7/lj7_h782_d1/lj7/kernel/kernel_device_modules-6.1/arch/arm64/boot/dts/mediatek/lj7_h782.dts
```

### 2.6 解析 `pre_platform_dts_path`（升级前 **平台** DTS，与 §2.5 独立）

按 [variables.md §5.3](../references/variables.md) 顺序执行（文件名 `{platform_name}.dts`，**禁止**与 `pre_project_dts_path` 混用）：

1. 若已有 `pre_project_dts_path` → 先试同目录 `{platform_name}.dts`。
2. 仓库根：`{base_code}/kernel/{kernel_modules_pre}/arch/arm64/boot/dts/mediatek/{platform_name}.dts`（`kernel_modules_pre` 由 `scenario` 决定，**不是** `kernel_old`）。
3. 在 `{base_code}/kernel/` 下 Glob `**/mediatek/{platform_name}.dts`。
4. 在 `tran_projects_root` 下 Glob `**/mediatek/{platform_name}.dts`。
5. 命中 1 个 → 写入变量确认表；命中多个 / 0 个 → 问开发者。

> 平台 DTS 供阶段 1 ADSP 检测只读；阶段 2 音频节点取值 **只读** `pre_project_dts_path`。

## 三、读软件配置表

把开发者给的 `sw_config_table` 图片/文本结构化抽取，至少包含下列字段（缺哪项就明确标出 `?`，**不要**自己脑补）：

| 字段 | 解析方式 |
| --- | --- |
| PA 型号 | 例：`AW87xxx` / `FS1599N`（**FS1588N 视作 FS1599N**） / `FS1589N` / `OCA72xxx` |
| SPK 个数 | 例：`1` / `2` |
| SPK PATH | 例：`LO` / `HP` |
| MIC 个数 | 例：`1` / `2` / ... |
| `PHONE_MIC_MODE` | `1`（AMIC）/ `2`（DMIC） |
| `HEADSET_MIC_MODE` | `1`（AMIC）/ `2`（DMIC） |
| TypeC 耳机？ | `yes` / `no` |
| `MTK_INCALL_HANDSFREE_DMNR` | `yes` / `no` / `?` |
| `MTK_VOIP_HANDSFREE_DMNR` | `yes` / `no` / `?` |
| `MTK_AURISYS_FRAMEWORK_SUPPORT` | `yes` / `no` / `?` |
| `MTK_BESLOUDNESS_SUPPORT` | `yes` / `no` / `?` |
| `MTK_BESLOUDNESS_RUN_WITH_HAL` | `yes` / `no` / `?` |
| `MTK_AUDIO_HD_REC_SUPPORT` | `yes` / `no` / `?` |

软件配置表 OCR 不清晰、字段值看不出 → **必须** 立刻问开发者，禁止"我猜应该是 X"。

## 四、输出「变量确认表」

按 [variables.md §7](../references/variables.md) 的表头给出一张表给开发者确认（举例）：

| 变量 | 推导结果 | 证据 | 待开发者确认 |
| --- | --- | --- | --- |
| `base_code` | `<由开发者提供>` | 直接输入 | √ |
| `base_code_sunmao` | `<由开发者提供>` | 直接输入 | √ |
| `scenario` | `vnd14_to_vnd14` | 直接输入 | √ |
| `project_name` | `cm7w_h616_64_bsp` | 切分自编译选项 | √ |
| `project_name1` | `cm7w` | 同上 | √ |
| `project_name_sunmao` | `cm7w_sunmao` | `{base_code_sunmao}/vendor/transsion/projects/` 唯一匹配前缀 `cm7w_` | √ |
| `platform_name` | `mt6878` | `MTK_PLATFORM := MT6878` 转小写 | √ |
| `kernel_old` | `kernel` | `tran_projects_root` 下直接子目录（lj7 为包装目录 `kernel`） | √ |
| `pre_project_dts_path` | `.../mediatek/lj7_h782.dts` | §5.2；仅 tran_projects | √ |
| `pre_platform_dts_path` | `.../mediatek/mt6878.dts` | §5.3；与项目 DTS 独立 | √ |

> 上表只是示例形态。`pre_project_dts_path` → 阶段 2 音频取值；`pre_platform_dts_path` → 阶段 1 ADSP 检测。**二者不可互换**。

同时附上「软件配置表抽取结果」，标注哪些字段是 `?`、哪些是清晰确认。

## 五、阶段 0 Checkpoint（开发者必须明确放行）

输出格式（按 [SKILL.md §输出契约](../SKILL.md) 三栏）：

| 项 | 内容 |
| --- | --- |
| 本阶段改了什么 | 无文件写入；产出"变量确认表" + "软件配置表抽取结果" |
| 还差什么 | 列出未确认变量与未抽出字段；列出 `audit_only` 与否的开关默认值 |
| 是否继续 | 默认询问开发者"是否进入阶段 1（修改 projects repo）？" |

## 六、跳出条款（阶段 0 专属）

- 升级前后侧目录布局明显不符合 SOP 模板（例如 `tran_projects/` 下嵌了 `branches/`、`device/transsion/` 与项目层都没有 `ProjectConfig.mk`） → 跳出，明确告知开发者"项目结构与 SOP 模板不一致，请确认是否仍按本 SOP 推进"。
- 软件配置表为图片但关键字段 OCR 不清晰、文字辨识 < 90% 把握 → 跳出，请开发者重新截图或提供文本。
- 开发者拒绝提供 `sw_config_table` → 跳出，告知"软件配置表是 SOP 的二级数据源，缺失意味着部分宏控只能完全依赖升级前文件，存在新机型新参数无法补齐的风险"。

## 七、本阶段必须遵守

- **不能**在本阶段写任何文件。
- **不能**为了"先开始干活"绕过未确认变量。
- **不能**把"推导失败"包装成"按默认值"——SKILL 必须显式让开发者看到推导失败的点。
