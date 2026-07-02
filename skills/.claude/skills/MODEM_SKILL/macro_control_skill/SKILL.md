---
name: macro-control-skill
description: 负责在代码A（原分支）和代码B（目标分支）的公共仓和私有仓中搜索并修改宏控代码，根据上下文变量进行宏控注入。支持 .h/.c/.cpp/.sh/.cfg/.json 文件。当用户提到 "宏控移植"、"宏控修改" 时触发。搜索必须使用 scripts/MacroSearch.ps1，注入必须使用 scripts/MacroInject.ps1，禁止自行构造搜索或修改命令。
version: 2.0.0
tools: Read, Glob, Grep, Edit, Bash
---

# 宏控子技能

## 技能定位
本技能是MODEM大版本升级的"工人"之一，负责执行公共仓和私有仓宏控代码的修改操作：
1. 直接接收主控技能传来的公共仓和私有仓路径以及上下文变量
2. 在公共仓和私有仓中搜索需要修改的宏控代码
3. 根据C语言编码规则和脚本文件格式进行宏控注入
4. 处理大小写不一致、空格差异、行末注释等复杂情况
5. 区分公共仓和私有仓的不同处理逻辑
6. 统计修改结果并返回给主控技能

## 输入参数
从主控技能接收以下参数：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Path_A_Pub | string | 代码A（原分支）的公共仓路径 |
| Path_A_Priv | string | 代码A（原分支）的私有仓路径 |
| Path_B_Pub | string | 代码B（目标分支）的公共仓路径 |
| Path_B_Priv | string | 代码B（目标分支）的私有仓路径 |
| X | string | RF参数版本号，从RF参数移植子技能获取 |
| Y | string | RF参数配置标识，从RF参数移植子技能获取 |
| BOM_Name | string | 原BOM名称，用于搜索 |
| BOM_Name_Target | string | 变更后的BOM名称，用于替换原BOM名称 |

## 执行流程
1. **验证输入参数**：检查Path_A_Pub、Path_A_Priv、Path_B_Pub、Path_B_Priv是否有效
2. **搜索原BOM名称**（使用 `scripts/MacroSearch.ps1`）：
   - 在原分支公共仓(Path_A_Pub)的mcu/custom目录下搜索
     - BOM名称格式：`__{BOM_Name}__`
     - 只搜索*.h, *.c, *.cpp文件
   - 在原分支私有仓(Path_A_Priv)中搜索
     - 搜索*.h, *.c, *.cpp, *.sh, *.cfg, *.json文件
   - 脚本自动捕获匹配行号、行内容、宏类型、上下文（前后3行），保存为JSON
3. **注入目标BOM名称**（使用 `scripts/MacroInject.ps1`）：
   - 采用双策略注入（优先级从高到低）：
     - **策略1 精确匹配**：目标文件中含旧BOM → 在旧BOM后注入（原有行为）
     - **策略2 上下文匹配**：目标文件中无旧BOM → 用搜索结果的上下文（前3行）在目标文件中定位，在对应行注入
     - **策略3 模式匹配兜底**：上下文匹配失败 → 按宏类型（#ifdef/#if defined/#elif defined等）在目标文件中找相同模式行注入
   - 公共仓：TargetBasePath=Path_B_Pub/mcu/custom，注入格式 ` || defined(__{BOM_Name_Target}__)`
   - 私有仓：TargetBasePath=Path_B_Priv，根据文件类型自动选择注入格式
   - 脚本自动处理：目标文件不存在跳过、已包含目标BOM跳过、已回导跳过
4. **结果统计**：解析脚本JSON输出，统计修改/跳过的文件数、位置和使用的策略
5. **返回结果**：将修改结果传递给主控技能

## 输出结果
| 输出项 | 类型 | 说明 |
|--------|------|------|
| success | boolean | 修改是否成功 |
| message | string | 执行结果描述 |
| modified_files | integer | 修改的文件数量 |
| modified_locations | integer | 修改的代码位置数量 |
| details | array | 修改详情列表 |

## 注意事项
- 需要处理大小写不一致的情况
- 需要处理多空格、少空格的差异
- 需要处理代码行很长不换行时在行末加注释的情况
- 修改前需要备份原始文件
- 复杂修改需要询问用户确认
