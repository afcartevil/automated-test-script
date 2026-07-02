---
name: project-file-skill
description: 修改 AP 工程文件 ProjectConfig.mk 中的 CUSTOM_MODEM 宏。当用户提到 "AP 工程文件修改"、"改 CUSTOM_MODEM" 时触发。只修改一个文件中的一个宏定义。必须使用 scripts/ModifyProjectConfig.ps1 脚本执行，禁止自行使用 Read/Edit 修改。
version: 2.0.0
tools: Read, Bash
---

# AP 工程文件修改子技能

## 技能概述
本技能负责修改 AP 侧工程文件，主要任务是更新 ProjectConfig.mk 文件中的 CUSTOM_MODEM 宏，确保其值为更新后的 BOM 仓名字。

## 输入参数
| 参数名 | 类型 | 描述 | 必填 |
|--------|------|------|------|
| BOM_Name_Target | string | 更新后的 BOM 仓名字（**从 MODEM_SKILL 继承**，无需用户重新输入） | 是 |
| AP_Project_Path | string | AP 工程文件代码路径（**用户重新输入**，示例：Z:\U-od\vendor\transsion\projects） | 是 |

## 输出结果
| 输出项 | 类型 | 描述 |
|--------|------|------|
| success | boolean | 操作是否成功 |
| message | string | 执行结果描述 |
| modified_file | string | 修改的文件路径 |
| original_value | string | 修改前的 CUSTOM_MODEM 值 |
| new_value | string | 修改后的 CUSTOM_MODEM 值 |

## 执行流程
1. **接收参数**：接收 BOM_Name_Target 和 AP_Project_Path 参数
2. **执行修改脚本**（使用 `scripts/ModifyProjectConfig.ps1`）：
   - 自动验证路径
   - 自动定位 ProjectConfig.mk
   - 自动修改 CUSTOM_MODEM 宏
   - 自动备份原文件
3. **返回结果**：返回执行结果

## 硬约束（必须遵守）
1. **修改只能用脚本**：必须通过 `scripts/ModifyProjectConfig.ps1` 执行。**禁止**自行使用 Read/Edit 或其他修改命令
2. **不读取脚本内容**：直接执行脚本即可，不需要阅读脚本源码

## 调用示例
```
powershell -ExecutionPolicy Bypass -File "scripts/ModifyProjectConfig.ps1" ^
    -BOM_Name_Target "{BOM_Name_Target}" ^
    -AP_Project_Path "{AP_Project_Path}"
```

## 异常处理
1. **AP_Project_Path 不存在**：脚本返回错误信息
2. **目标文件夹不存在**：脚本返回错误信息
3. **ProjectConfig.mk 文件不存在**：脚本返回错误信息
4. **CUSTOM_MODEM 宏未找到**：脚本返回错误信息
5. **值已是目标值**：脚本返回"已设置"，不做修改