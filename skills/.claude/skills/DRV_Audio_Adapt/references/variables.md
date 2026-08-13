# 变量与路径模板

本表是 SOP 中所有 `{xxx}` 变量的唯一定义。其他 `references/` 与 `workflows/` 中出现的变量替换语义以本表为准。

## 1. 顶层输入变量

| 变量 | 含义 | 来源 |
| --- | --- | --- |
| `base_code` | 升级前 vnd 代码分支绝对路径 | 开发者直接给 |
| `base_code_sunmao` | 升级后 vnd 代码分支绝对路径 | 开发者直接给 |
| `scenario` | `vnd12_to_vnd16` 或 `vnd14_to_vnd14` | 开发者直接给 |
| `project_compile_option` | 升级前的项目编译选项串（如 `cm7w_h616_64_bsp`） | 开发者给文本或截图 |
| `sw_config_table` | 软件配置表（截图或文本） | 开发者给 |

> 三段输入不强制一次给齐。任一缺失 → 主动追问开发者，**不臆造**。

## 2. 从 `project_compile_option` 切分得到的项目名变量

将 `project_compile_option` 按下划线 `_` 切分：

- 第 1 段 → `project_name1`
- 第 2 段 → `project_name2`
- 第 3 段 → `project_name3`
- 第 N 段 → `project_nameN`
- 全名（原串） → `project_name`

示例：`cm7w_h616_64_bsp` →

- `project_name1 = cm7w`
- `project_name2 = h616`
- `project_name3 = 64`
- `project_name4 = bsp`
- `project_name = cm7w_h616_64_bsp`

## 3. 从升级后侧推导：`project_name_sunmao`

在 `{base_code_sunmao}/vendor/transsion/projects/` 目录下搜索 **包含 `project_name1`（且尽量长匹配 `project_name`）** 的目录名作为 `project_name_sunmao`。

候选策略：

1. 先做精确匹配：目录名 `== project_name`。命中即采纳。
2. 否则按前缀匹配：目录名以 `project_name1_` 开头，取唯一一项。命中多项 → 必须问开发者，不要自己挑。
3. 否则按包含匹配：目录名包含 `project_name1`。命中多项 → 必须问开发者。
4. 全部未命中 → 报告"升级后侧未发现项目目录"，请开发者确认升级后侧是否已建项目目录。

> 不要把 `project_name_sunmao` 与 `project_name` 混为一谈——后者来自编译选项串，前者来自升级后侧实际目录名，二者可能不同（例如升级后侧目录改名加平台前/后缀）。

## 4. 从升级后侧推导：`platform_name`

读取 `{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/ProjectConfig.mk`，找 `MTK_PLATFORM = <value>` 一行，把 `<value>` **全部转小写** 作为 `platform_name`。

> 如果该行不存在或值不可读：先在同目录下其他 `ProjectConfig*.mk`（`ProjectConfig_overlay.mk` / `ProjectConfig_BSP.mk`）里再找一次；仍无 → 必须问开发者。

示例：`MTK_PLATFORM = MT6878` → `platform_name = mt6878`

## 5. DTS 路径推导（升级前侧）：项目 DTS ≠ 平台 DTS

**二者是不同文件、不同用途、不同解析流程，禁止混用或互相替代。**

| 维度 | 升级前项目 DTS | 升级前平台 DTS |
| --- | --- | --- |
| 文件名 | `{project_name_sunmao}.dts` | `{platform_name}.dts` |
| 典型用途 | 阶段 2：PA / TypeC / GPIO / `tran_audio_controller` **取值** | 阶段 1：ADSP 检测（`snd_audio_dsp` / `mtk-dsp-type`），**只读** |
| 解析变量 | `pre_project_dts_path`（§5.2） | `pre_platform_dts_path`（§5.3） |
| 搜索根目录 | **仅** `tran_projects_root` | 仓库根 `{base_code}/kernel/` 为主；可与项目 DTS **同目录**候选 |
| 禁止 | 用仓库根 `kernel/**/{project_name_sunmao}.dts` 替代 | 用 `pre_project_dts_path` 或 `{project_name_sunmao}.dts` 替代 |

### 5.0 固定前缀：`tran_projects_root`

```
tran_projects_root = {base_code}/tran_projects/{project_name1}/{project_name}/{project_name1}/
```

> **升级前项目 DTS 一定在 `tran_projects` 下**（§5.2）。**升级前平台 DTS 不在此约束内**（§5.3），通常位于仓库根 `kernel/` 树。

### 5.1 推导 `kernel_old`（仅第一层目录名）

在 `tran_projects_root` 下，列**直接子目录**，取 **以 `kernel` 开头** 的目录名作为 `kernel_old`：

- 通常形如 `kernel-5.15` / `kernel-6.1` / `kernel_device_modules-6.1` / **`kernel`**（包装目录）。
- **禁止**把内层目录名（如 `kernel_device_modules-6.1`）当成 `kernel_old`，除非它本身就是 `tran_projects_root` 的直接子目录。
- 命中多个 → 问开发者；命中 0 个 → 跳出 SOP，问开发者。

示例（lj7）：

- `tran_projects_root` = `.../tran_projects/lj7/lj7_h782_d1/lj7/`
- `kernel_old` = **`kernel`**（不是 `kernel_device_modules-6.1`）

### 5.2 解析 `pre_project_dts_path`（升级前项目 DTS，强制顺序）

记模板路径：

```
pre_project_dts_tpl = {tran_projects_root}/{kernel_old}/arch/arm64/boot/dts/mediatek/{project_name_sunmao}.dts
```

按下列顺序解析，**前一步命中即停止**：

1. **模板直拼**：若 `pre_project_dts_tpl` 存在 → `pre_project_dts_path = pre_project_dts_tpl`。
2. **`tran_projects_root` 下搜索**（模板未命中时 **必须**执行，禁止改去仓库根 `kernel/`）：
   - 用 Glob 在 `tran_projects_root` 下搜索：`**/arch/arm64/boot/dts/mediatek/{project_name_sunmao}.dts`
   - 或等价：`**/{project_name_sunmao}.dts`（限定在 `tran_projects_root` 内）。
   - 命中 **1** 个 → 采纳为 `pre_project_dts_path`。
   - 命中 **多个** → 必须问开发者（附完整路径列表）。
   - 命中 **0** 个 → 跳出 SOP，问开发者。
3. **禁止兜底**：不得使用 `{base_code}/kernel/**/{project_name_sunmao}.dts` 作为升级前项目 DTS。

lj7 实测路径（步骤 1 未命中、步骤 2 命中）：

```
{base_code}/tran_projects/lj7/lj7_h782_d1/lj7/kernel/kernel_device_modules-6.1/arch/arm64/boot/dts/mediatek/lj7_h782.dts
```

> `kernel_old = kernel` 时，内层还有 `kernel_device_modules-6.1/`，属于「双层 kernel 布局」。此时以 Glob 命中的 `pre_project_dts_path` 为准，并在阶段 0 变量确认表中写明完整路径。

阶段 0 变量确认表除 `kernel_old` 外，**必须**增加 `pre_project_dts_path` 与 `pre_platform_dts_path`（各含完整绝对路径 + 采用的解析步骤）。

### 5.3 解析 `pre_platform_dts_path`（升级前平台 DTS，与 §5.2 独立）

记 `kernel_modules_pre`（按 `scenario`，与 `kernel_old` **无关**）：

| `scenario` | `kernel_modules_pre` |
| --- | --- |
| `vnd14_to_vnd14` | `kernel_device_modules-6.1` |
| `vnd12_to_vnd16` | `kernel_device_modules-6.12` |

按下列顺序解析 `pre_platform_dts_path`（文件名 **必须** 为 `{platform_name}.dts`），**前一步命中即停止**：

1. **与项目 DTS 同目录**（若已解析出 `pre_project_dts_path`）：  
   `{dirname(pre_project_dts_path)}/{platform_name}.dts`
2. **仓库根 kernel 树模板**（平台 DTS 常见落位）：  
   `{base_code}/kernel/{kernel_modules_pre}/arch/arm64/boot/dts/mediatek/{platform_name}.dts`
3. **`{base_code}/kernel/` 下 Glob**：  
   `**/arch/arm64/boot/dts/mediatek/{platform_name}.dts`
4. **`tran_projects_root` 下 Glob**（部分项目把平台 dtsi 同步进 tran_projects）：  
   `**/arch/arm64/boot/dts/mediatek/{platform_name}.dts`
5. 命中 **1** 个 → 采纳；命中 **多个** → 问开发者；命中 **0** 个 → 跳出 SOP，问开发者。

**禁止**：

- 用 `pre_project_dts_path`（`{project_name_sunmao}.dts`）做 ADSP / 平台属性检测。
- 把 `kernel_old`（tran_projects 第一层目录名，如 `kernel`）代入 `{base_code}/kernel/{kernel_old}/arch/...` 拼平台路径（会得到 `kernel/kernel/arch/...` 等错误路径）。
- 用升级后平台 DTS 作为升级前 ADSP 检测源。

## 6. 全部路径模板（替换上面变量即得最终路径）

### 6.1 升级前侧（`{base_code}`）

- ProjectConfig 类（搜索宏控用，全部都要试）：
  - `{base_code}/device/transsion/{project_name_sunmao}/ProjectConfig.mk`
  - `{base_code}/tran_projects/{project_name1}/{project_name}/{project_name1}/device/transsion/{project_name_sunmao}/ProjectConfig.mk`
  - `{base_code}/tran_projects/{project_name1}/{project_name}/{project_name1}/device/transsion/{project_name_sunmao}/ProjectConfig_overlay.mk`
  - `{base_code}/tran_projects/{project_name1}/{project_name}/{project_name1}/device/transsion/{project_name_sunmao}/ProjectConfig_BSP.mk`
- 升级前 PA 文件根目录：`{base_code}/device/transsion/{project_name_sunmao}/`
- 升级前 **项目** DTS：**`pre_project_dts_path`**（§5.2；仅 `tran_projects_root`）
- 升级前 **平台** DTS：**`pre_platform_dts_path`**（§5.3；与项目 DTS 独立解析）
- 升级前平台 audio_device.xml：`{base_code}/device/mediatek/{platform_name}/audio_device.xml`
- 升级前项目 audio_device.xml：`{base_code}/device/transsion/{project_name_sunmao}/audio_device.xml`
- 升级前 aurisys_config_rv.xml 候选：
  - `{base_code}/device/transsion/{project_name_sunmao}/audio/aurisys_config_rv.xml`
  - `{base_code}/device/mediatek/{platform_name}/aurisys_config_rv.xml`
- 升级前 aurisys_config_hifi3.xml 候选：
  - `{base_code}/device/transsion/{project_name_sunmao}/aurisys_config_hifi3.xml`
  - `{base_code}/device/transsion/{project_name_sunmao}/audio/aurisys_config_hifi3.xml`
  - `{base_code}/device/mediatek/{platform_name}/aurisys_config_hifi3.xml`
- 升级前 DWS（双场景共用一个路径模板）：
  - `{base_code}/tran_projects/{project_name1}/{project_name}/{project_name1}/vendor/mediatek/proprietary/tools/dct/dws/{platform_name}/{project_name_sunmao}.dws`

### 6.2 升级后侧（`{base_code_sunmao}`，榫卯）

- ProjectConfig.mk：`{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/ProjectConfig.mk`
- 项目 audio 根目录（PA 文件落位）：`{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/audio/`
- 升级后项目 audio_device.xml：`{base_code_sunmao}/vendor/transsion/projects/{project_name_sunmao}/audio/audio_device.xml`
- 升级后平台 audio_device.xml（作为基线）：`{base_code_sunmao}/device/mediatek/{platform_name}/audio_device.xml`
- 升级后 **项目** DTS（阶段 2 修改目标，`post_project_dts_path`）：
  - `vnd14_to_vnd14`：`{base_code_sunmao}/kernel/kernel_device_modules-6.1/arch/arm64/boot/dts/mediatek/{project_name_sunmao}.dts`
  - `vnd12_to_vnd16`：`{base_code_sunmao}/kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/{project_name_sunmao}.dts`
- 升级后 **平台** DTS（`post_platform_dts_path`，仅只读对照；**禁止**作为升级前 ADSP 检测源）：
  - `vnd14_to_vnd14`：`{base_code_sunmao}/kernel/kernel_device_modules-6.1/arch/arm64/boot/dts/mediatek/{platform_name}.dts`
  - `vnd12_to_vnd16`：`{base_code_sunmao}/kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/{platform_name}.dts`
- 升级后 DWS：
  - preloader：`{base_code_sunmao}/vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/{project_name_sunmao}/dct/dct/codegen.dws`
  - tools/dct：`{base_code_sunmao}/vendor/mediatek/proprietary/tools/dct/dws/{platform_name}/{project_name_sunmao}.dws`
  - proprietary/custom：`{base_code_sunmao}/vendor/mediatek/proprietary/custom/{project_name_sunmao}/kernel/dct/dct/codegen.dws`
- 升级后工模配置：`{base_code_sunmao}/vendor/mediatek/proprietary/custom/{project_name_sunmao}/factory/factory.ini`

## 7. 变量确认表（阶段 0 必须给开发者看）

| 变量 | 推导结果 | 证据（来自哪条路径/哪个字段） | 开发者确认 |
| --- | --- | --- | --- |
| `base_code` | | 开发者直接给 | |
| `base_code_sunmao` | | 开发者直接给 | |
| `scenario` | | 开发者直接给 | |
| `project_name` | | 切分 `project_compile_option` | |
| `project_name1` | | 同上 | |
| `project_name_sunmao` | | `{base_code_sunmao}/vendor/transsion/projects/` 子目录 | |
| `platform_name` | | `{base_code_sunmao}/.../{project_name_sunmao}/ProjectConfig.mk` 的 `MTK_PLATFORM` | |
| `kernel_old` | | `tran_projects_root` 下以 `kernel` 开头的**直接**子目录名 | |
| `pre_project_dts_path` | | §5.2；`{project_name_sunmao}.dts`，仅 `tran_projects_root` | |
| `pre_platform_dts_path` | | §5.3；`{platform_name}.dts`，与项目 DTS 独立 | |

任一字段无法填出 → 阶段 0 必须停下，问开发者，不进入阶段 1。
