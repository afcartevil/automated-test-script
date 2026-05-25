# 锁卡NV修改子技能执行工作流

## 工作流概述
本工作流定义了锁卡NV修改子技能的详细执行步骤，严格遵循C语言宏控逻辑，确保在目标分支公共仓中准确修改锁卡相关的NV参数配置。

## 执行步骤

### 步骤1：接收参数
- 从主控技能接收以下参数：
  - Path_B_Pub: 代码B（目标分支）的公共仓路径
  - BOM_Name_Target: 变更后的BOM名称，用于添加宏控

### 步骤2：路径验证
- 检查Path_B_Pub是否存在且可访问
- 若路径无效，返回错误信息给主控技能

### 步骤3：定义修改目标配置
根据C语言宏控逻辑参考文档，定义以下修改目标：

**sml_public_def.h 修改目标（10处）：**
| 序号 | 目标宏定义 | 文件路径 |
|------|-----------|---------|
| 1 | `#define SML_SL_BLOB_TIME_STAMP_SIZE             8` | mcu/interface/protocol/general/sml_public_def.h |
| 2 | `#define SML_SL_BLOB_LENGTH_SIZE                 2` | mcu/interface/protocol/general/sml_public_def.h |
| 3 | `#define SML_SL_BLOB_SIZE_OF_SIGNATURE           256` | mcu/interface/protocol/general/sml_public_def.h |
| 4 | `#define SML_SL_NVRAM_ACCESS_ID_UPDATE_LOCK_OP   0xFB` | mcu/interface/protocol/general/sml_public_def.h |
| 5 | `#define SML_SL_BLOB_SIZE_OF_CAT_SP     7` | mcu/interface/protocol/general/sml_public_def.h |
| 6 | `#define SML_SL_BLOB_MAX_SUPPORT_CAT_SP     10` | mcu/interface/protocol/general/sml_public_def.h |
| 7 | `#define SML_SL_BLOB_CAT_SP_SIZE         (SML_SL_BLOB_MAX_SUPPORT_CAT_SP * SML_SL_BLOB_SIZE_OF_CAT_SP)` | mcu/interface/protocol/general/sml_public_def.h |
| 8 | `kal_uint8   time_stamp[SML_SL_BLOB_TIME_STAMP_SIZE];` | mcu/interface/protocol/general/sml_public_def.h |
| 9 | `kal_uint8   code_cat_sp[SML_SL_BLOB_CAT_SP_SIZE];` | mcu/interface/protocol/general/sml_public_def.h |
| 10 | `kal_uint8   signature[SML_SL_BLOB_SIZE_OF_SIGNATURE];` | mcu/interface/protocol/general/sml_public_def.h |

**l4_nvram_def.h 修改目标（2处）：**
| 序号 | 目标宏定义 | 文件路径 |
|------|-----------|---------|
| 1 | `#define NVRAM_EF_SML_S_LID_VERNO    "001"` | mcu/interface/service/nvram/l4_nvram_def.h |
| 2 | `#define NVRAM_EF_SML_S_LID_HASH   0x4E0B7529` | mcu/interface/service/nvram/l4_nvram_def.h |

**l4_nvram_editor.h 修改目标（3处）：**
| 序号 | 目标宏定义 | 文件路径 |
|------|-----------|---------|
| 1 | `time_stamp:"[DOC, RUNTIME]Time stamp value in BLOB"` | mcu/interface/service/nvram/l4_nvram_editor.h |
| 2 | `code_cat_sp:"[DOC, RUNTIME]Service Provider Configuration code: MCC-MNC-GID triplets"` | mcu/interface/service/nvram/l4_nvram_editor.h |
| 3 | `signature:"[DOC, RUNTIME]Signature: Verification code used for blob validation"` | mcu/interface/service/nvram/l4_nvram_editor.h |

### 步骤4：定义C语言宏控修改函数
定义通用的宏控修改函数，严格遵循C语言语法规则，特别注意注释处理：

```powershell
Function AddMacroControl {
    param(
        [string]$filePath,
        [string]$targetMacro,
        [string]$bomNameTarget
    )
    
    # 检查文件是否存在
    if (-not (Test-Path $filePath)) {
        Write-Warning "文件不存在: $filePath"
        return @{ success = $false; message = "文件不存在" }
    }
    
    # 备份原始文件
    $backupPath = "$filePath.backup"
    Copy-Item -Path $filePath -Destination $backupPath -Force
    
    # 读取文件内容
    $content = Get-Content -Path $filePath -Raw
    
    # 定义要添加的宏控
    $macroToAdd = " || defined(__${bomNameTarget}__)"
    
    # 检查目标宏是否已包含该宏控
    if ($content -match "__${bomNameTarget}__") {
        Write-Information "目标宏控已存在: __${bomNameTarget}__"
        return @{ success = $true; message = "宏控已存在，无需修改"; changed = $false }
    }
    
    # 构建正则表达式模式：匹配目标宏定义行，然后匹配后续的#if defined行
    # 注意：跳过纯注释行（以 // 或 /* 开头）
    $pattern = [regex]::Escape($targetMacro) + "(\s*\n(?![ \t]*//|/\*).*?)*?\n(#if\s+defined\([^)]+\)[^\n]*)"
    
    # 执行替换
    $match = [regex]::Match($content, $pattern)
    if ($match.Success) {
        $fullMatch = $match.Value
        $ifLine = $match.Groups[2].Value
        
        # 处理行内注释：如果#if行包含//注释，宏控应添加在注释之前
        $commentPart = ""
        $codePart = $ifLine
        
        # 检测是否包含//注释
        $commentIndex = $ifLine.IndexOf("//")
        if ($commentIndex -gt 0) {
            # 提取注释部分
            $commentPart = $ifLine.Substring($commentIndex)
            # 提取代码部分（//之前的内容）
            $codePart = $ifLine.Substring(0, $commentIndex).TrimEnd()
        }
        
        # 在代码部分末尾添加宏控
        $newCodePart = $codePart + $macroToAdd
        # 重新拼接：代码部分 + 注释部分
        $newIfLine = $newCodePart + $commentPart
        
        $newContent = $content.Replace($fullMatch, $fullMatch.Replace($ifLine, $newIfLine))
        
        # 保存修改后的文件
        Set-Content -Path $filePath -Value $newContent -NoNewline
        
        return @{ success = $true; message = "修改成功"; changed = $true }
    } else {
        Write-Warning "未找到目标宏定义或后续的#if defined行: $targetMacro"
        # 恢复备份
        Copy-Item -Path $backupPath -Destination $filePath -Force
        return @{ success = $false; message = "未找到目标位置" }
    }
}
```

### 步骤5：执行修改（sml_public_def.h）
```powershell
$filePath = Join-Path $Path_B_Pub "mcu/interface/protocol/general/sml_public_def.h"

$targetMacros = @(
    "#define SML_SL_BLOB_TIME_STAMP_SIZE             8",
    "#define SML_SL_BLOB_LENGTH_SIZE                 2",
    "#define SML_SL_BLOB_SIZE_OF_SIGNATURE           256",
    "#define SML_SL_NVRAM_ACCESS_ID_UPDATE_LOCK_OP   0xFB",
    "#define SML_SL_BLOB_SIZE_OF_CAT_SP     7",
    "#define SML_SL_BLOB_MAX_SUPPORT_CAT_SP     10",
    "#define SML_SL_BLOB_CAT_SP_SIZE         (SML_SL_BLOB_MAX_SUPPORT_CAT_SP * SML_SL_BLOB_SIZE_OF_CAT_SP)",
    "kal_uint8   time_stamp[SML_SL_BLOB_TIME_STAMP_SIZE];",
    "kal_uint8   code_cat_sp[SML_SL_BLOB_CAT_SP_SIZE];",
    "kal_uint8   signature[SML_SL_BLOB_SIZE_OF_SIGNATURE];"
)

foreach ($macro in $targetMacros) {
    $result = AddMacroControl -filePath $filePath -targetMacro $macro -bomNameTarget $BOM_Name_Target
    if (-not $result.success) {
        Write-Warning "修改失败: $($result.message) - $macro"
    }
}
```

### 步骤6：执行修改（l4_nvram_def.h）
```powershell
$filePath = Join-Path $Path_B_Pub "mcu/interface/service/nvram/l4_nvram_def.h"

$targetMacros = @(
    '#define NVRAM_EF_SML_S_LID_VERNO    "001"',
    '#define NVRAM_EF_SML_S_LID_HASH   0x4E0B7529'
)

foreach ($macro in $targetMacros) {
    $result = AddMacroControl -filePath $filePath -targetMacro $macro -bomNameTarget $BOM_Name_Target
    if (-not $result.success) {
        Write-Warning "修改失败: $($result.message) - $macro"
    }
}
```

### 步骤7：执行修改（l4_nvram_editor.h）
```powershell
$filePath = Join-Path $Path_B_Pub "mcu/interface/service/nvram/l4_nvram_editor.h"

$targetMacros = @(
    'time_stamp:"[DOC, RUNTIME]Time stamp value in BLOB"',
    'code_cat_sp:"[DOC, RUNTIME]Service Provider Configuration code: MCC-MNC-GID triplets"',
    'signature:"[DOC, RUNTIME]Signature: Verification code used for blob validation"'
)

foreach ($macro in $targetMacros) {
    $result = AddMacroControl -filePath $filePath -targetMacro $macro -bomNameTarget $BOM_Name_Target
    if (-not $result.success) {
        Write-Warning "修改失败: $($result.message) - $macro"
    }
}
```

### 步骤8：C语言语法验证
```powershell
# 验证修改后的C语言语法
$filesToVerify = @(
    Join-Path $Path_B_Pub "mcu/interface/protocol/general/sml_public_def.h",
    Join-Path $Path_B_Pub "mcu/interface/service/nvram/l4_nvram_def.h",
    Join-Path $Path_B_Pub "mcu/interface/service/nvram/l4_nvram_editor.h"
)

foreach ($file in $filesToVerify) {
    if (Test-Path $file) {
        # 使用gcc检查语法（如果可用）
        try {
            gcc -fsyntax-only $file 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Information "语法检查通过: $file"
            } else {
                Write-Warning "语法检查失败: $file"
            }
        } catch {
            Write-Information "gcc不可用，跳过语法检查: $file"
        }
    }
}
```

### 步骤9：结果统计
- 统计成功修改的文件数量（最多3个文件）
- 统计成功修改的代码位置数量（最多15处）
- 记录每个修改的详细信息

### 步骤10：返回结果
- 组织返回数据结构：
  - success: 布尔值，表示执行是否成功
  - message: 执行结果描述
  - modified_files: 修改的文件数量
  - modified_locations: 修改的代码位置数量
  - details: 修改详情列表

## C语言宏控逻辑规则（参考references/c_macro_logic_reference.md）

### 修改模式
1. 搜索目标宏定义（如 `#define SML_SL_BLOB_TIME_STAMP_SIZE 8`）
2. 定位到该宏定义所在行
3. 向下查找，找到第一个以 `#if defined(` 开头的条件编译行
4. 在该行末尾追加 `|| defined(__{BOM_Name_Target}__)`

### 边界情况处理
- **目标宏定义未找到**：跳过该宏定义，记录警告信息
- **后续无#if defined(指令**：跳过该宏定义，记录警告信息
- **目标文件不存在**：跳过该文件，记录错误信息
- **文件已包含目标宏控**：跳过该修改点，记录信息

### 安全机制
- 修改前自动备份原始文件（.backup后缀）
- 检查文件写入权限
- 支持事务性修改（失败时自动恢复备份）

## 输出示例
```json
{
  "success": true,
  "message": "锁卡NV修改完成，共修改3个文件，15处代码",
  "modified_files": 3,
  "modified_locations": 15,
  "details": [
    {
      "file": "mcu/interface/protocol/general/sml_public_def.h",
      "changes": 10,
      "status": "success"
    },
    {
      "file": "mcu/interface/service/nvram/l4_nvram_def.h",
      "changes": 2,
      "status": "success"
    },
    {
      "file": "mcu/interface/service/nvram/l4_nvram_editor.h",
      "changes": 3,
      "status": "success"
    }
  ]
}
```