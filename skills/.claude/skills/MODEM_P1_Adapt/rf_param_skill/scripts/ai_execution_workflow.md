# RF参数移植子技能执行工作流

## 工作流概述
本工作流定义了RF参数移植子技能的详细执行步骤，用于从代码A（原分支）提取RF参数并移植到代码B（目标分支）。

## 输入参数
- Path_A_Priv: 代码A（原分支）的私有仓路径
- Path_A_Pub: 代码A（原分支）的公共仓路径
- Path_B_Priv: 代码B（目标分支）的私有仓路径
- Path_B_Pub: 代码B（目标分支）的公共仓路径
- BOM_Name: 项目的BOM名称（如ae10_h833_a1, cm7_h781, x6870_h781_f1, lk7k_h582）
- BOM_Name_Target: 变更后的BOM名称（如x6856_h971_a1）
- RF_TARGET_LOCATION: RF参数目标位置（public/private）

## 执行步骤

### 步骤1：验证输入路径
- 检查Path_A_Priv是否存在且可访问
- 检查Path_A_Pub是否存在且可访问
- 检查Path_B_Priv是否存在且可访问
- 检查Path_B_Pub是否存在且可访问
- 若路径无效，返回错误信息给主控技能

### 步骤2：智能发现RF参数位置

#### 阶段A：尝试读取.json文件（优先）

**检查公共仓projects目录：**
```
路径: {Path_A_Pub}/projects/
操作: 列出所有.json文件
命令: dir /b {Path_A_Pub}\projects\*.json
```

**检查私有仓projects目录：**
```
路径: {Path_A_Priv}/projects/
操作: 列出所有.json文件
命令: dir /b {Path_A_Priv}\projects\*.json
```

**解析.json文件：**
若找到.json文件，解析以下字段：
- project_name: 项目名称
- rf_param_path: RF参数相对于projects的路径
- rf_version (X): RF参数版本号
- config_id (Y): 配置标识

**成功条件：**
- 找到.json文件
- 解析出有效的project_name和rf_param_path
- rf_param_path指向的位置必须存在

#### 阶段B：grep搜索（备选方案）

若.json文件不存在或解析失败，执行grep搜索：

**搜索私有仓projects目录：**
```
路径: {Path_A_Priv}/projects/
命令: Get-ChildItem -Path {Path_A_Priv}\projects -Recurse -Directory | Where-Object {$_.Name -eq "{BOM_Name}"}
```

**搜索公共仓projects目录：**
```
路径: {Path_A_Pub}/projects/
命令: Get-ChildItem -Path {Path_A_Pub}\projects -Recurse -Directory | Where-Object {$_.Name -eq "{BOM_Name}"}
```

**BOM名称匹配规则：**
- 精确匹配：文件夹名称必须完全等于BOM_Name
- 禁止模糊匹配：如"lk7k_h582"不能匹配"lk7k_h582_f1"
- 常见BOM格式：ae10_h833_a1, cm7_h781, x6870_h781_f1, lk7k_h582

### 步骤3：确认项目文件夹位置

**单匹配情况：**
- 直接使用找到的路径

**多匹配情况：**
- 向用户展示所有匹配结果
- 请求用户选择正确的项目文件夹
- 格式示例：
  ```
  找到多个匹配的文件夹，请确认：
  1. D:\project\mp_release_10.0\private\projects\ae10_h833_a1
  2. D:\project\mp_release_10.0\private\projects\sub\ae10_h833_a1
  请输入序号选择：_
  ```

**未匹配情况：**
- 返回错误信息，告知用户未找到匹配的BOM文件夹

### 步骤4：定位RF参数文件

在确认的原项目文件夹下搜索RF参数文件：

**搜索RF参数文件：**
```
文件名模式：
- *_rf_param_*.xml
- rf_parameters_*.cfg
- *radio_config*.dat
- *RF*.xml

命令：
Get-ChildItem -Path "{原项目路径}" -Recurse -Include "*rf_param*","*RF*","*radio_config*" -File
```

### 步骤5：确定目标位置并创建文件夹

**确定目标仓：**
根据用户指定的RF_TARGET_LOCATION确定目标位置：
- 若目标为公共仓：使用Path_B_Pub
- 若目标为私有仓：使用Path_B_Priv

**创建目标文件夹：**
```
目标路径: {目标仓路径}/projects/{BOM_Name_Target}/
操作: 创建目录（若不存在）
```

### 步骤6：复制RF参数文件

**复制策略：**
- 使用PowerShell Copy-Item命令直接复制整个目录
- 使用递归和强制覆盖选项
- 直接复制所有文件，不进行复杂验证

**复制命令：**
```powershell
# 直接复制整个目录，递归复制所有文件和子目录
Copy-Item -Path "{原项目路径}\*" -Destination "{目标仓路径}/projects/{BOM_Name_Target}/" -Recurse -Force
```

**说明：**
- 使用 `-Recurse` 参数递归复制所有子目录和文件
- 使用 `-Force` 参数强制覆盖已存在的文件
- 支持文件名包含括号、空格、特殊符号等特殊字符
- 直接复制，保持原有的目录结构

**操作: 复制所有RF参数文件，保持目录结构**

### 步骤7：更新目标分支.json文件

**确定目标仓.json文件路径：**
- 若RF_TARGET_LOCATION=public：目标仓为Path_B_Pub
- 若RF_TARGET_LOCATION=private：目标仓为Path_B_Priv

**查找.json文件：**
```powershell
$jsonFiles = Get-ChildItem -Path "{目标仓路径}/projects" -Filter "*.json" -Recurse
```

**读取并更新.json文件：**
```powershell
$jsonContent = Get-Content -Path "{json文件路径}" -Raw | ConvertFrom-Json

# 更新字段
$jsonContent.modem_bom = "{BOM_Name_Target}"
$jsonContent.mtk_project_name = "{目标分支公共仓名称}"
$jsonContent.is_tran_project = if ("{RF_TARGET_LOCATION}" -eq "public") { "n" } else { "y" }

# 保存更新后的.json文件
$jsonContent | ConvertTo-Json -Depth 10 | Set-Content -Path "{json文件路径}"
```

**字段说明：**
- modem_bom: 设置为变更后的BOM名称（BOM_Name_Target）
- mtk_project_name: 设置为目标分支的公共仓名称（如TK_MD_MOLY.NR17.R1.MP3.RC.MP_U0）
- is_tran_project: 若RF_TARGET_LOCATION=public则设为"n"，若=private则设为"y"

### 步骤8：提取上下文变量

从RF参数文件中提取变量X和Y：

**X（RF参数版本号）：**
- 通常在文件头或特定字段中
- 格式示例：RF_V2.1.0, V2.1.0, 2.1.0

**Y（RF参数配置标识）：**
- 通常为配置ID或类型标识
- 格式示例：CONFIG_TYPE_A, A, TYPE_A

### 步骤9：返回结果

组织返回数据结构：
```json
{
  "success": true,
  "message": "RF参数移植成功，从Priv移植到Pub，共复制5个文件",
  "source_location": "Priv",
  "target_location": "Pub",
  "file_count": 5,
  "variables": {
    "X": "RF_V2.1.0",
    "Y": "CONFIG_TYPE_A"
  }
}
```

## 决策分支

### 分支1：路径验证失败
- 返回错误信息
- 终止执行

### 分支2：未找到.json且grep无结果
- 返回警告信息
- 询问用户是否手动指定项目路径

### 分支3：多个匹配结果
- 向用户展示选项
- 等待用户选择
- 根据选择继续执行

### 分支4：目标文件夹已存在
- 询问用户是否覆盖
- 根据用户选择执行相应操作

## 异常处理

- **文件复制失败**：记录错误文件，继续复制其他文件
- **变量提取失败**：使用默认值或提示用户手动输入
- **权限不足**：提示用户检查权限
- **JSON解析失败**：回退到grep搜索方案

## 输出示例

```json
{
  "success": true,
  "message": "RF参数移植成功，从私有仓移植到公共仓，共复制5个文件",
  "source_location": "Priv",
  "target_location": "Pub",
  "file_count": 5,
  "variables": {
    "X": "RF_V2.1.0",
    "Y": "CONFIG_TYPE_A"
  }
}
```

## 错误输出示例

```json
{
  "success": false,
  "message": "未找到BOM名称为lk7k_h582的项目文件夹",
  "error_code": "BOM_NOT_FOUND",
  "suggestion": "请检查BOM名称是否正确，或手动指定项目路径"
}
```
