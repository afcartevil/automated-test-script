# RF参数移植子技能执行工作流

## 工作流概述
从代码A（原分支）提取RF参数并移植到代码B（目标分支）。

## 输入参数
- Path_A_Priv: 代码A（原分支）的私有仓路径
- Path_A_Pub: 代码A（原分支）的公共仓路径
- Path_B_Priv: 代码B（目标分支）的私有仓路径
- Path_B_Pub: 代码B（目标分支）的公共仓路径
- BOM_Name: 项目的BOM名称
- BOM_Name_Target: 变更后的BOM名称
- RF_TARGET_LOCATION: RF参数目标位置（public/private）

## 执行步骤

### 步骤0：参数接收
直接从用户输入中获取所有参数。**不要逐个询问用户，用户会一次性提供全部参数**。

### 步骤1：验证输入路径
检查 4 个路径是否都存在。任一不存在则终止执行，返回错误。

### 步骤2：智能发现RF参数位置（调用 RfSearch.ps1，禁止自行搜索）

**必须且只能通过执行 RfSearch.ps1 脚本完成搜索：**

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/RfSearch.ps1" "{Path_A_Pub}" "{Path_A_Priv}" "{BOM_Name}"
```

脚本内部已按以下顺序执行4步搜索（你不需要自行构造额外的搜索命令）：
1. `{Path_A_Pub}/projects/*.json` → 找到则返回，未找到继续
2. `{Path_A_Priv}/projects/*.json` → 找到则返回，未找到继续
3. `{Path_A_Pub}/projects/` 目录 grep → 找到则返回，未找到继续
4. `{Path_A_Priv}/projects/` 目录 grep → 找到则返回，均未找到则返回 `found = false`

**解析脚本 JSON 输出**：
- `found = false` → 报错"未找到BOM名称为 {BOM_Name} 的项目文件夹"，终止
- `source = "json"` → 从 JSON 中读取 project_name、rf_param_path、rf_version(X)、config_id(Y)
- `source = "grep"` 且 `multiple = true` → 向用户展示所有匹配结果，等待选择
- `source = "grep"` 且 `multiple = false` → 直接使用返回的 path

### 步骤3：确认项目文件夹位置

根据步骤2脚本返回的结果：
- 单匹配：直接使用返回的 path 作为源项目路径
- 多匹配：向用户展示所有匹配，等待用户选择
- 未匹配：返回错误，终止执行

### 步骤4：列出源文件夹下所有文件（必须完整列出）

**防止文件遗漏的关键步骤。**

```powershell
Get-ChildItem -Path "{源项目路径}" -Recurse -File | Select-Object -ExpandProperty FullName
```

**必须列出全部文件，特别关注**：
- **根级 .ini 文件**（如 `TK_MD(LWCG_R2_6789).ini`，在源项目目录根级，不在 mcu/ 下）
- **根级 .cfg 文件**（如 `TMDK.cfg`，在源项目目录根级，不在 mcu/ 下）
- `mcu/` 目录下的所有文件
- 其他所有子目录中的文件

**禁止**：只列出 mcu/ 而忽略根级 .ini/.cfg、使用 Glob 代替 Get-ChildItem -Recurse -File。

### 步骤5：确定目标位置（严格根据 RF_TARGET_LOCATION）

| RF_TARGET_LOCATION | 目标路径 |
|-------------------|---------|
| `public` | `{Path_B_Pub}\projects\{BOM_Name_Target}` |
| `private` | `{Path_B_Priv}\projects\{BOM_Name_Target}` |

**禁止**：无视 RF_TARGET_LOCATION 自行判断、使用 Path_B_Pub/Path_B_Priv 之外的路径、根据"哪个存在选哪个"。

### 步骤6：复制文件（调用 RfCopy.ps1，禁止自行复制）

**必须调用 RfCopy.ps1 脚本。禁止自行使用 robocopy、Copy-Item、xcopy 等命令。**

该脚本内部已实现：
1. 创建目标目录（如不存在）
2. robocopy /E 完整复制
3. .ini/.cfg/mcu 完整性验证
4. 缺失文件自动补复制
5. 最终文件数量对比
6. JSON 格式输出结果

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/RfCopy.ps1" -SourcePath "{源项目路径}" -TargetPath "{目标路径}"
```

**解析脚本 JSON 输出**：
- `success = true` + `files_match = true` → 复制成功，进入步骤7
- `success = false` → 报错终止，错误信息在 `error` 字段中

### 步骤7：验证复制结果

确认步骤6脚本返回的 JSON 中以下字段均为 true：
- `success`
- `files_match`
- `ini_verified`
- `cfg_verified`
- `mcu_verified`

任一为 false 则报错终止。

### 步骤8：更新目标分支.json文件

根据 RF_TARGET_LOCATION 确定目标仓的 .json 文件路径。读取并更新以下字段：
- modem_bom → BOM_Name_Target
- mtk_project_name → 目标分支公共仓名称
- is_tran_project → public 则为 "n"，private 则为 "y"

### 步骤9：提取上下文变量

从步骤2脚本返回的 JSON 中提取：
- X = rf_version（RF参数版本号）
- Y = config_id（RF参数配置标识）

如果脚本未返回这些值，从 RF 参数文件中查找。

### 步骤10：返回结果

```json
{
  "success": true,
  "message": "RF参数移植成功",
  "source_location": "Priv或Pub",
  "target_location": "Priv或Pub",
  "file_count": <数量>,
  "variables": { "X": "<值>", "Y": "<值>" }
}
```

## 执行检查清单

| 步骤 | 检查项 | 通过标准 |
|------|--------|---------|
| 步骤2 | 搜索是否覆盖两侧 | RfSearch.ps1 已执行并返回结果 |
| 步骤4 | 文件列表是否完整 | 列出了所有根级文件（含 .ini/.cfg）+ mcu/ 所有文件 |
| 步骤5 | 目标路径是否正确 | 路径中包含 RF_TARGET_LOCATION 对应的 Path_B_Pub 或 Path_B_Priv |
| 步骤6 | 复制是否完整 | RfCopy.ps1 返回 success=true, files_match=true |
| 步骤7 | 验证是否通过 | ini_verified=true, cfg_verified=true, mcu_verified=true |

## 硬约束（必须遵守）

1. **搜索只能用 RfSearch.ps1**：步骤2的搜索**必须**通过执行 `RfSearch.ps1` 完成。禁止自行构造 Get-ChildItem、Select-String 或其他搜索命令。
2. **复制只能用 RfCopy.ps1**：步骤6的文件复制**必须**通过执行 `RfCopy.ps1` 完成。禁止自行使用 robocopy、Copy-Item 或 xcopy 等命令。
3. **公共仓→私有仓两侧必搜**：RfSearch.ps1 脚本内部已实现4步搜索。只有两侧都未找到时才返回 `found = false`。
4. **BOM名称精确匹配**：禁止模糊匹配。
5. **目标仓严格按 RF_TARGET_LOCATION**：`public` → Path_B_Pub，`private` → Path_B_Priv。禁止自行判断。
6. **不要逐个询问用户参数**：用户会一次性提供所有参数，直接开始执行。
