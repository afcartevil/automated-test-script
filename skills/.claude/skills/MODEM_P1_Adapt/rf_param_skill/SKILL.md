# RF参数移植子技能

## 基本信息
- **name**: RF参数移植子技能
- **description**: 负责从代码A（原分支）提取RF参数文件，并移植到代码B（目标分支）。智能发现RF参数位置：优先读取projects目录下的.json文件获取项目信息，若无.json文件则在projects目录下grep搜索BOM名称对应的文件夹。适用于RF参数移植、版本升级、项目迁移等场景。
- **version**: 1.0.0
- **env**:
  - model: claude-3-5-sonnet
  - python_version: 3.11+
  - dependencies: []

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

## 智能发现RF参数位置流程

### 步骤1：读取.json文件（优先）
在以下路径查找.json文件：
- `{Path_A_Priv}/projects/*.json`
- `{Path_A_Pub}/projects/*.json`
- `{Path_B_Priv}/projects/*.json`
- `{Path_B_Pub}/projects/*.json`

从.json文件中解析：
- 项目名称（project name）
- RF参数位置（RF parameter path）
- 上下文变量X和Y

### 步骤2：grep搜索（备选）
若.json文件不存在或解析失败，则在projects目录下执行grep搜索：

搜索命令：`dir /s /b *{BOM_Name}*` 或 `find . -name "*{BOM_Name}*"`

**注意**：
- BOM名称需要精确匹配（全字匹配），避免匹配到类似但不同的项目
- 搜索结果可能有多个，需要向用户确认正确的项目文件夹

### 步骤3：确认RF参数位置
根据.json解析或grep搜索结果，确定：
- 原RF参数位置（Path_A_Priv或Path_A_Pub下的projects/{BOM_Name}/）
- 目标RF参数位置（Path_B_Priv或Path_B_Pub下的projects/{BOM_Name}/）

## 执行流程
1. **验证输入路径**：检查4个路径是否有效
2. **智能发现RF参数**：
   - 优先读取.json文件
   - 若无.json文件则grep搜索BOM名称
   - 向用户确认正确的项目文件夹（如有多个匹配）
3. **定位RF参数文件**：在原项目目录下查找RF参数文件
4. **创建目标文件夹**：在目标分支的projects下创建BOM_Name_Target文件夹（使用变更后的BOM名称）
5. **复制文件**：将RF参数文件复制到目标文件夹
6. **更新目标分支.json文件**：
   - 根据RF_TARGET_LOCATION确定目标仓（public或private）
   - 读取目标仓的.json文件
   - 更新以下字段：
     - modem_bom: 设置为BOM_Name_Target
     - mtk_project_name: 设置为目标分支的公共仓名称
     - is_tran_project: 若RF_TARGET_LOCATION=public则设为"n"，若=private则设为"y"
7. **提取变量**：从RF参数中提取上下文变量X和Y
8. **返回结果**：将变量X和Y传递给主控技能

## 输出结果
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

## 注意事项
- BOM名称需要精确匹配，避免grep到其他类似项目
- RF参数文件通常包含特定命名模式（如*_rf_param_*.xml）
- 复制文件时需保持原有的目录结构
- 执行完毕后，必须明确地将变量X和Y"交接"给主控技能
- 使用Robocopy命令进行文件复制，支持特殊字符文件名（如括号、空格等）
- 复制完成后会进行文件数量对比验证，确保无遗漏
- 若发现文件数量不一致，会自动单独复制缺失的文件
- 目标文件夹使用变更后的BOM名称（BOM_Name_Target）命名
- 会自动更新目标分支的.json文件，更新modem_bom、mtk_project_name、is_tran_project字段
