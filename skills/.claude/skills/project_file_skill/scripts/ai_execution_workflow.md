# AP 工程文件修改子技能执行工作流

## 工作流概述
本工作流定义了 AP 工程文件修改子技能的完整执行流程，主要任务是更新 ProjectConfig.mk 文件中的 CUSTOM_MODEM 宏。

## 执行步骤

### 步骤 1：接收参数
接收来自主控技能或用户的输入参数：
- **BOM_Name_Target**：更新后的 BOM 仓名字（**从 MODEM_SKILL 继承**，无需用户重新输入）
- **AP_Project_Path**：AP 工程文件代码路径（**用户重新输入**）

### 步骤 2：执行修改（使用 ModifyProjectConfig.ps1）
```
powershell -ExecutionPolicy Bypass -File "scripts/ModifyProjectConfig.ps1" ^
    -BOM_Name_Target "{BOM_Name_Target}" ^
    -AP_Project_Path "{AP_Project_Path}"
```

脚本内部完成：
1. 验证 AP_Project_Path 是否存在
2. 查找 `{AP_Project_Path}/{BOM_Name_Target}/ProjectConfig.mk`
3. 读取文件内容，查找 `CUSTOM_MODEM = ...` 宏
4. 如果当前值已是目标值，直接返回成功（不修改）
5. 否则备份原文件，修改宏值为 BOM_Name_Target
6. 返回修改结果

### 步骤 3：返回结果
解析脚本返回的 JSON 输出，返回：
- success: 是否成功
- message: 执行结果描述
- modified_file: 修改的文件路径
- original_value: 修改前的值
- new_value: 修改后的值
- changed: 是否实际发生了修改

## 硬约束（必须遵守）
1. **修改只能用脚本**：必须通过 `ModifyProjectConfig.ps1` 执行。**禁止**自行使用 Read/Edit 或其他修改命令
2. **不读取脚本内容**：直接执行脚本即可，不需要阅读脚本源码

## 异常处理
1. **路径不存在**：脚本返回错误信息
2. **文件夹不存在**：脚本返回错误信息
3. **文件不存在**：脚本返回错误信息
4. **宏未找到**：脚本返回错误信息

## 输出示例

### 成功修改
```json
{
  "success": true,
  "message": "CUSTOM_MODEM updated from 'CUSTOM_MODEM = old_bom' to 'new_bom'",
  "modified_file": "Z:\\U-od\\vendor\\transsion\\projects\\new_bom\\ProjectConfig.mk",
  "original_value": "CUSTOM_MODEM = old_bom",
  "new_value": "CUSTOM_MODEM = new_bom",
  "changed": true
}
```

### 已是目标值
```json
{
  "success": true,
  "message": "CUSTOM_MODEM already set to new_bom",
  "modified_file": "Z:\\U-od\\vendor\\transsion\\projects\\new_bom\\ProjectConfig.mk",
  "original_value": "CUSTOM_MODEM = new_bom",
  "new_value": "CUSTOM_MODEM = new_bom",
  "changed": false
}
```

### 失败
```json
{
  "success": false,
  "error": "CUSTOM_MODEM macro not found in Z:\\...\\ProjectConfig.mk"
}
```
