---
name: rf-param-skill
description: 负责从代码A（原分支）提取RF参数文件，并移植到代码B（目标分支）。当用户提到 "RF 参数移植"、"RF 移植" 时触发。搜索项目位置必须使用 scripts/RfSearch.ps1 脚本，禁止自行构造搜索命令。文件复制使用 robocopy。必须严格搜索公共仓→私有仓两侧，必须严格按 RF_TARGET_LOCATION 决定目标仓路径，必须复制项目目录下的全部文件（含 .ini/.cfg/mcu 等）。
version: 1.0.0
tools: Read, Glob, Grep, Bash
---

# RF参数移植子技能

## 技能定位
本技能是MODEM大版本升级的"工人"之一，负责执行RF参数的移植操作：
1. 直接接收主控技能传来的路径参数
2. 智能发现原分支和目标分支的RF参数位置（通过.json文件或grep搜索）
3. 在目标分支创建新项目目录
4. 复制RF参数文件到目标位置
5. 提取上下文变量X和Y并传递回主控技能

## BOM名称格式
项目BOM名称示例（用于grep搜索）：
- `ae10_h833_a1`
- `cm7_h781`
- `x6870_h781_f1`
- `lk7k_h582`

**注意**：需要精确匹配BOM名称，避免grep错误匹配其他项目。

## 输入参数
从主控技能接收以下参数：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Path_A_Priv | string | 代码A（原分支）的私有仓路径 |
| Path_A_Pub | string | 代码A（原分支）的公共仓路径 |
| Path_B_Priv | string | 代码B（目标分支）的私有仓路径 |
| Path_B_Pub | string | 代码B（目标分支）的公共仓路径 |
| BOM_Name | string | 项目的BOM名称，用于定位项目文件夹 |
| BOM_Name_Target | string | 变更后的BOM名称，用于命名目标分支项目文件夹 |
| RF_TARGET_LOCATION | string | RF参数目标位置（public/private） |

## 【硬约束】RF_TARGET_LOCATION → 目标仓路径映射表（不可偏离）

当用户指定 RF_TARGET_LOCATION 后，目标仓路径**只能**是以下两个之一，**没有任何例外、没有任何自主判断空间**：

| RF_TARGET_LOCATION 的值 | 目标仓路径（必须且只能用此路径） |
|------------------------|--------------------------|
| `public` | `{Path_B_Pub}\projects\{BOM_Name_Target}` |
| `private` | `{Path_B_Priv}\projects\{BOM_Name_Target}` |

**绝对禁止**：
- 禁止无视 RF_TARGET_LOCATION 自行选择目标仓
- 禁止根据"哪个路径存在就选哪个"来决定目标仓
- 禁止使用 Path_B_Pub / Path_B_Priv 之外的任何其他路径
- 禁止将目标路径设在项目目录之外的任何位置
- 如果 RF_TARGET_LOCATION = `public`，目标路径**必须**包含 Path_B_Pub，否则立即终止并报错

## 【硬约束】RF参数搜索顺序（公共仓→私有仓，两侧必搜）

**搜索顺序固定为以下 4 步，每一步都必须执行，禁止跳过或提前终止：**

| 步骤 | 搜索位置 | 搜索方式 | 找到后 | 未找到时 |
|------|---------|---------|--------|---------|
| 1 | `{Path_A_Pub}/projects/*.json` | 读JSON | 返回结果 | 继续步骤2 |
| 2 | `{Path_A_Priv}/projects/*.json` | 读JSON | 返回结果 | 继续步骤3 |
| 3 | `{Path_A_Pub}/projects/` 目录 | Get-ChildItem grep | 返回结果 | 继续步骤4 |
| 4 | `{Path_A_Priv}/projects/` 目录 | Get-ChildItem grep | 返回结果 | 报错终止 |

**关键规则**：
- 步骤1 没找到 ≠ 搜索结束，**必须继续步骤2、3、4**
- 只有步骤1~4 全部未找到时，才报错 "未找到BOM名称为 {BOM_Name} 的项目文件夹"
- 执行 RfSearch.ps1 脚本时，脚本内部已实现上述4步顺序，直接调用即可
- 禁止在调用 RfSearch.ps1 之外自行构造 Get-ChildItem、Select-String 等搜索命令

## 【硬约束】RF参数文件复制（全量复制，不可遗漏）

RF参数项目目录下通常包含以下文件和目录，**必须全部复制，一个都不能少**：

**根级文件示例**（以 x6850_h895_f1_v 项目为例）：
- `TK_MD(LWCG_R2_6789).ini` — 配置文件
- `TMDK.cfg` — 配置文件

**子目录**：
- `mcu/` — RF参数主目录（含 custom/l1/cl1_rf/ 等大量子文件）

**复制要求**：
1. 步骤4 必须列出源目录下**所有文件**（根级 + 子目录），不能只列出 mcu/ 下的文件
2. 步骤7 必须验证源文件总数 = 目标文件总数
3. 步骤7 必须单独验证 .ini 文件是否存在于目标路径
4. 步骤7 必须单独验证 .cfg 文件是否存在于目标路径
5. 如果源有 50 个文件、目标只有 48 个，**必须找出缺失的 2 个并单独复制**

## 执行流程（严格按顺序执行，不可跳过或合并步骤）

### 步骤0：参数接收
直接从用户输入中获取以下参数。**不要逐个询问，用户会一次性提供所有参数**：
- Path_A_Pub, Path_A_Priv, Path_B_Pub, Path_B_Priv
- BOM_Name, BOM_Name_Target
- RF_TARGET_LOCATION

### 步骤1：验证输入路径
检查 4 个路径是否全部存在且可访问。如有路径不存在，**立即终止执行**并告知用户，不要尝试后续步骤。

### 步骤2：智能发现RF参数位置（必须严格按搜索顺序执行）

**执行 RfSearch.ps1 脚本**（该脚本内部已实现：公共仓JSON→私有仓JSON→公共仓grep→私有仓grep 的4步搜索）：

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/RfSearch.ps1" "{Path_A_Pub}" "{Path_A_Priv}" "{BOM_Name}"
```

脚本输出为 JSON，解析以下字段：
- `found` (bool): 是否找到
- `source`: "json" 或 "grep"
- `search_source` 或 `source`: "Pub" 或 "Priv"（表示在原分支的公共仓还是私有仓找到）
- `path`: 找到的项目文件夹路径（grep 方式时）
- `rf_param_path`: RF参数路径（JSON 方式时）
- `rf_version`: 上下文变量 X
- `config_id`: 上下文变量 Y

**如果脚本返回 `found = false`，报错终止，不要自行构造其他搜索命令。**

### 步骤3：确认项目文件夹位置并向用户展示
展示找到的源路径，等待用户确认（如多匹配让用户选择）。

### 步骤4：列出源文件夹下所有文件（必须完整列出，禁止遗漏）

在确认的源项目目录下执行：

```powershell
Get-ChildItem -Path "{源项目路径}" -Recurse -File | Select-Object -ExpandProperty FullName
```

**必须列出全部文件，包括但不限于**：
- **根级 .ini 文件**（如 `TK_MD(LWCG_R2_6789).ini`）
- **根级 .cfg 文件**（如 `TMDK.cfg`）
- `mcu/` 目录下的所有文件
- 其他所有子目录中的文件

**禁止行为**：
- 禁止只列出 mcu/ 下的文件而忽略根级 .ini/.cfg
- 禁止使用 Glob 工具代替 Get-ChildItem -Recurse -File
- 禁止只列出部分文件就进入下一步

### 步骤5：确定目标位置（必须严格根据 RF_TARGET_LOCATION 参数）

| RF_TARGET_LOCATION 的值 | 目标仓路径（必须使用此路径） |
|------------------------|--------------------------|
| `public` | `{Path_B_Pub}\projects\{BOM_Name_Target}` |
| `private` | `{Path_B_Priv}\projects\{BOM_Name_Target}` |

**禁止行为**：
- 禁止无视 RF_TARGET_LOCATION 自行选择目标仓
- 禁止使用 Path_B_Pub / Path_B_Priv 之外的任何其他路径
- 禁止根据"哪个路径存在就选哪个"来决定目标仓

### 步骤6：复制文件（必须调用 RfCopy.ps1 脚本）

**禁止自行使用 robocopy 或 Copy-Item。必须调用 scripts/RfCopy.ps1 脚本，该脚本内部已实现：**
- robocopy 完整复制
- .ini/.cfg/mcu 完整性验证
- 缺失文件自动补复制
- 最终文件数量对比验证

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/RfCopy.ps1" -SourcePath "{源项目路径}" -TargetPath "{目标路径}"
```

脚本输出为 JSON，解析以下字段：
- `success` (bool): 复制是否成功
- `source_file_count`: 源文件总数
- `target_file_count`: 目标文件总数
- `files_match` (bool): 文件数量是否一致
- `ini_verified` / `cfg_verified` / `mcu_verified` (bool): 各类文件是否验证通过
- `supplemental_copied`: 补复制的文件数
- `error`: 错误信息（失败时）

**如果脚本返回 `success = false`，报错终止，不要自行重试。**

### 步骤7：验证复制结果

解析步骤6脚本返回的 JSON，确认：
- `success = true`
- `files_match = true`
- `ini_verified = true`
- `cfg_verified = true`
- `mcu_verified = true`

以上任一为 false 则报错终止。

### 步骤8：更新目标分支.json文件
根据 RF_TARGET_LOCATION 确定目标仓的 .json 文件路径，更新 modem_bom、mtk_project_name、is_tran_project 字段。

### 步骤9：提取上下文变量 X 和 Y
从步骤2的搜索结果或RF参数文件中提取，传递给主控技能。

### 步骤10：返回结果
| 输出项 | 类型 | 说明 |
|--------|------|------|
| success | boolean | 移植是否成功 |
| message | string | 执行结果描述 |
| source_location | string | 原RF参数位置（Priv/Pub） |
| target_location | string | 目标RF参数位置（Priv/Pub） |
| file_count | integer | 复制的文件数量 |
| variables | object | 上下文变量对象 |
| variables.X | string | RF参数版本号 |
| variables.Y | string | RF参数配置标识 |

## 输出结果
