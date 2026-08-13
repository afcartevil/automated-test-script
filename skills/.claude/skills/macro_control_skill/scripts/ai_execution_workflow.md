# 宏控子技能执行工作流

## 工作流概述
本工作流在代码A（原分支）和代码B（目标分支）的公共仓和私有仓中搜索并修改BOM名称相关的宏控代码。

## 执行步骤

### 步骤1：接收参数
从主控技能接收以下参数：
- Path_A_Pub: 代码A（原分支）的公共仓路径
- Path_A_Priv: 代码A（原分支）的私有仓路径
- Path_B_Pub: 代码B（目标分支）的公共仓路径
- Path_B_Priv: 代码B（目标分支）的私有仓路径
- BOM_Name: 原BOM名称
- BOM_Name_Target: 变更后的BOM名称

### 步骤2：路径验证
检查 4 个路径是否都存在。任一不存在则终止执行，返回错误。

### 步骤3：搜索原BOM名称（使用 MacroSearch.ps1）

**公共仓搜索**：
```
powershell -ExecutionPolicy Bypass -File "scripts/MacroSearch.ps1" "{Path_A_Pub}\mcu\custom" "__{BOM_Name}__" ".h,.c,.cpp"
```

**私有仓搜索**：
```
powershell -ExecutionPolicy Bypass -File "scripts/MacroSearch.ps1" "{Path_A_Priv}" "{BOM_Name}" ".h,.c,.cpp,.sh,.cfg,.json"
```

搜索结果包含：匹配行号、行内容、宏类型、上下文（前3行 + 后3行）。将两次搜索结果分别保存为 JSON 文件（如 `pub_search.json` 和 `priv_search.json`）。

### 步骤4：注入目标BOM名称（使用 MacroInject.ps1）

对公共仓和私有仓分别执行注入脚本：

**公共仓注入**（.h/.c/.cpp 文件，注入 `|| defined(__{BOM_Name_Target}__)`）：
```
powershell -ExecutionPolicy Bypass -File "scripts/MacroInject.ps1" ^
    -TargetBasePath "{Path_B_Pub}\mcu\custom" ^
    -SourceBasePath "{Path_A_Pub}\mcu\custom" ^
    -SourceResultsFile "pub_search.json" ^
    -BOM_Name_Target "{BOM_Name_Target}"
```

**私有仓注入**（.h/.c/.cpp/.sh/.cfg/.json 文件）：
```
powershell -ExecutionPolicy Bypass -File "scripts/MacroInject.ps1" ^
    -TargetBasePath "{Path_B_Priv}" ^
    -SourceBasePath "{Path_A_Priv}" ^
    -SourceResultsFile "priv_search.json" ^
    -BOM_Name_Target "{BOM_Name_Target}"
```

**注入策略**（按优先级）：
1. **精确匹配**：目标文件包含旧BOM → 在旧BOM后直接注入（原有行为）
2. **上下文匹配**：目标文件不含旧BOM → 用搜索结果的 `contextBefore`（前3行）在目标文件中匹配，在对应行注入
3. **模式匹配兜底**：上下文匹配失败 → 按 `macroType`（#ifdef/#if defined/#elif defined等）在目标文件中找相同模式行注入

解析两次注入的 JSON 输出，获取修改/跳过统计和使用的策略信息。

### 步骤5：结果统计
- 搜索到的文件总数
- 实际修改的文件数（按策略分类：精确匹配/上下文匹配/模式匹配）
- 跳过的文件数（已修改/回导/目标不存在/不含锁卡NV文件/无任何匹配）

### 步骤6：返回结果
```json
{
  "success": true,
  "message": "宏控代码修改完成",
  "modified_files": <数量>,
  "skipped_files": <数量>,
  "details": [<修改详情>]
}
```

## 硬约束（必须遵守）

1. **搜索和注入只能用脚本**：步骤3必须通过 `MacroSearch.ps1`，步骤4必须通过 `MacroInject.ps1`。**禁止**自行构造 Select-String、grep、Edit 或其他搜索/修改命令
2. **不读取脚本内容**：直接执行脚本即可，不需要阅读脚本源码
3. **不修改锁卡NV文件**：MacroSearch.ps1 内部已排除 `sml_public_def.h`、`l4_nvram_def.h`、`l4_nvram_editor.h`，不需要额外处理
4. **不修改 IMEI 防篡改相关文件**：`errc_nvram_def.c` 的 IMEI 防篡改逻辑已有专门方案支持，MacroInject.ps1 内部已排除，不需要额外处理
5. **搜索结果都为空时**：返回警告信息，终止执行
6. **注入结果中 modifiedCount=0 且 totalCount>0 时**：输出警告，说明所有目标文件都已包含目标BOM或文件内容完全不同
