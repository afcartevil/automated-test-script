# 公共仓宏控子技能执行工作流

## 工作流概述
本工作流定义了宏控子技能的详细执行步骤，用于在代码A（原分支）和代码B（目标分支）的公共仓和私有仓中搜索并修改BOM名称相关的宏控代码。支持搜索多种文件类型，包括源代码文件和脚本文件。

## 执行步骤

### 步骤1：接收参数
- 从主控技能接收以下参数：
  - Path_A_Pub: 代码A（原分支）的公共仓路径
  - Path_A_Priv: 代码A（原分支）的私有仓路径
  - Path_B_Pub: 代码B（目标分支）的公共仓路径
  - Path_B_Priv: 代码B（目标分支）的私有仓路径
  - X: RF参数版本号
  - Y: RF参数配置标识
  - BOM_Name: 原BOM名称，用于搜索
  - BOM_Name_Target: 变更后的BOM名称，用于替换原BOM名称

### 步骤2：路径验证
- 检查Path_A_Pub是否存在且可访问
- 检查Path_A_Priv是否存在且可访问
- 检查Path_B_Pub是否存在且可访问
- 检查Path_B_Priv是否存在且可访问
- 若路径无效，返回错误信息给主控技能

### 步骤3：搜索原BOM名称
- 在原分支公共仓(Path_A_Pub)中搜索包含原BOM名称(BOM_Name)的文件
- 在原分支私有仓(Path_A_Priv)中搜索包含原BOM名称(BOM_Name)的文件
- 搜索的文件类型包括：*.h, *.c, *.cpp, *.sh, *.cfg, *.json
- 排除log文件和其他不需要的文件类型
- 公共仓只搜索mcu/custom目录下的文件
- 私有仓搜索整个目录
- 记录所有匹配的文件路径

**搜索命令（公共仓）：**
```powershell
# 在原分支公共仓中搜索包含原BOM名称的文件
# BOM名称在代码中使用双下划线格式：__{BOM_Name}__
# 排除log文件，只搜索mcu/custom目录下的配置文件
Get-ChildItem -Path "{Path_A_Pub}/mcu/custom" -Recurse -File -Include "*.h","*.c","*.cpp" | Select-String -Pattern "__{BOM_Name}__" | Select-Object Path -Unique
```

**搜索命令（私有仓）：**
```powershell
# 在原分支私有仓中搜索包含原BOM名称的文件
# 支持多种文件类型：源代码文件和脚本文件
$pattern = "{BOM_Name}"
Get-ChildItem -Path "{Path_A_Priv}" -Recurse -File -Include "*.h","*.c","*.cpp","*.sh","*.cfg","*.json" | Select-String -Pattern $pattern | Select-Object Path -Unique
```

### 步骤4：定位目标文件
- 根据原分支公共仓找到的文件路径，提取相对路径
- 在目标分支公共仓(Path_B_Pub)中定位对应的文件
- 根据原分支私有仓找到的文件路径，提取相对路径
- 在目标分支私有仓(Path_B_Priv)中定位对应的文件
- 记录需要修改的目标文件列表（区分公共仓和私有仓）

### 步骤5：智能甄别与替换BOM名称
- 遍历所有目标文件（公共仓和私有仓）
- 在修改前，先读取目标分支对应文件的内容
- 分析宏控逻辑，判断是否需要添加或修改：
  - 检查目标分支是否已经做了回导（所有项目都支持该功能）
  - 如果目标分支已经做了回导，则不需要宏控，跳过修改
  - 如果目标分支没有做回导，则需要添加宏控逻辑
  - 如果目标分支有类似的宏控逻辑但BOM名称不同，则替换BOM名称
- **公共仓处理**：使用双下划线格式 `__{BOM_Name}__` 进行替换
- **私有仓处理**：根据文件类型使用不同的替换格式：
  - 源代码文件(.h, .c, .cpp)：使用双下划线格式 `__{BOM_Name}__`
  - 脚本文件(.sh)：使用原始格式 `{BOM_Name}`
- 将原BOM名称替换为变更后的BOM名称(BOM_Name_Target)

**智能甄别规则：**
1. **检查目标分支是否已做回导**：
   - 分析原分支文件中的宏控逻辑（如 `#ifdef`、`#define`、条件编译等）
   - 检查目标分支对应文件是否已经移除了类似的宏控逻辑
   - 如果目标分支已经移除了宏控逻辑（说明已做回导，所有项目都支持），则跳过修改
   - 如果目标分支仍然保留宏控逻辑，则继续检查

2. **检查是否已包含变更后的BOM名称**：
   - 如果目标文件已经包含 `BOM_Name_Target`，则跳过修改
   - 避免重复添加相同的BOM名称

3. **检查宏控逻辑是否适用于目标分支**：
   - 如果目标分支仍然需要宏控逻辑（未做回导），则替换BOM名称
   - 如果目标分支有类似的宏控逻辑但BOM名称不同，则替换BOM名称

**智能甄别命令（公共仓）：**
```powershell
# 读取目标文件内容
$targetContent = Get-Content -Path "{目标文件路径}" -Raw

# BOM名称在代码中使用双下划线格式：__{BOM_Name}__
$originalPattern = "__{BOM_Name}__"
$targetPattern = "__{BOM_Name_Target}__"

# 检查目标分支是否已做回导（移除了宏控逻辑）
# 如果目标分支已经移除了宏控逻辑，说明所有项目都支持，不需要宏控
if ($targetContent -notmatch "相关的宏控逻辑模式") {
    Write-Host "目标分支已做回导，所有项目都支持，不需要宏控，跳过修改"
    continue
}

# 检查目标文件是否已经包含变更后的BOM名称（带双下划线格式）
if ($targetContent -match $targetPattern) {
    Write-Host "目标文件已包含变更后的BOM名称，跳过修改"
    continue
}

# 读取文件内容并替换BOM名称（带双下划线格式）
$content = Get-Content -Path "{目标文件路径}" -Raw
$content = $content.Replace($originalPattern, $originalPattern + " || defined(" + $targetPattern + ")")
$content | Set-Content -Path "{目标文件路径}"
```

**智能甄别命令（私有仓）：**
```powershell
# 读取目标文件内容
$targetContent = Get-Content -Path "{目标文件路径}" -Raw

# 根据文件类型确定搜索模式
$fileExtension = [System.IO.Path]::GetExtension("{目标文件路径}")

if ($fileExtension -match "\.(h|c|cpp)$") {
    # 源代码文件：使用双下划线格式
    $originalPattern = "__{BOM_Name}__"
    $targetPattern = "__{BOM_Name_Target}__"
} else {
    # 脚本文件：使用原始格式
    $originalPattern = "{BOM_Name}"
    $targetPattern = "{BOM_Name_Target}"
}

# 检查目标文件是否已经包含变更后的BOM名称
if ($targetContent -match [regex]::Escape($targetPattern)) {
    Write-Host "目标文件已包含变更后的BOM名称，跳过修改"
    continue
}

# 读取文件内容并替换BOM名称
$content = Get-Content -Path "{目标文件路径}" -Raw
$content = $content.Replace($originalPattern, $targetPattern)
$content | Set-Content -Path "{目标文件路径}"
```

### 步骤6：结果统计
- 统计修改的文件数量
- 统计修改的代码位置数量
- 记录每个修改的详细信息

### 步骤7：返回结果
- 组织返回数据结构：
  - success: 布尔值，表示执行是否成功
  - message: 执行结果描述
  - modified_files: 修改的文件数量
  - modified_locations: 修改的代码位置数量
  - details: 修改详情列表

## 决策分支
1. **路径验证失败**：
   - 返回错误信息
   - 终止执行
2. **未找到包含原BOM名称的文件**：
   - 返回警告信息
   - 告知用户未找到需要修改的宏控代码
3. **目标文件不存在**：
   - 跳过该文件，继续处理其他文件
   - 记录警告信息

## 异常处理
- 文件读取失败：跳过该文件，继续处理其他文件
- 文件写入失败：记录错误，尝试其他方法
- 权限不足：提示用户检查权限

## 输出示例
```json
{
  "success": true,
  "message": "宏控代码修改完成，共修改2个文件，5处代码",
  "modified_files": 2,
  "modified_locations": 5,
  "details": [
    {
      "file": "platform/common/macros.h",
      "changes": [
        "替换BOM名称: d9300evb_h890a_a1 -> d9300evb_h890a"
      ]
    }
  ]
}
```
