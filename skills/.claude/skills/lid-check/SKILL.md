---
name: "lid-check"
description: "检查 MTK 项目 cgen/inc 下 Custom_NvRam_LID.h 枚举与 CFG_file_info_custom.h 数组中的 LID 是否一一对应、顺序一致、无缺漏。当用户要求检查 LID 缺失、NV 标志位偏移、cgen LID 对应关系时调用。"
funcType: "AI自动化适配"
category: "驱动"
---

# LID 缺失检查

## 概述

本 Skill 用于检查 MTK 平台项目中 `cgen/inc` 目录下的 NVRAM LID 配置是否存在缺失或顺序错误。LID 缺失会导致 NV 标志位集体偏移，出现写入数组越界或无法读取的问题。

## 背景

- **问题现象**：某些标志位操作出现写入数组越界/无法读取
- **根因**：MTK 原生代码缺失一个 LID，导致 NV 标志位集体偏移
- **参考案例**：CM7 占位标记 TPS 闪退

## 检查流程

### 步骤 1：定位目标目录

找到对应项目路径：
```
vendor/mediatek/proprietary/custom/<project>/cgen/
```

目标文件：
- `inc/Custom_NvRam_LID.h` — CUSTOM_CFG_FILE_LID 枚举定义
- `inc/CFG_file_info_custom.h` — TCFG_FILE g_akCFG_File_Custom[] 数组定义

### 步骤 2：提取枚举 LID 列表

打开 `inc/Custom_NvRam_LID.h`，提取 `CUSTOM_CFG_FILE_LID` 枚举中的所有 LID（排除 `AP_CFG_CUSTOM_FILE_MAX_LID` 终止符）。

示例格式：
```c
typedef enum
{
    AP_CFG_RDCL_FILE_AUDIO_LID=AP_CFG_CUSTOM_BEGIN_LID,
    AP_CFG_CUSTOM_FILE_GPS_LID,
    // ...
    AP_CFG_CUSTOM_FILE_MAX_LID,
} CUSTOM_CFG_FILE_LID;
```

### 步骤 3：提取数组 LID 列表

打开 `inc/CFG_file_info_custom.h`，提取 `g_akCFG_File_Custom[]` 数组中每条记录使用的 `VER(AP_CFG_xxx_LID)`。

示例格式：
```c
const TCFG_FILE g_akCFG_File_Custom[]=
{
    {
        "/mnt/vendor/nvdata/media/Audio_Sph", VER(AP_CFG_RDCL_FILE_AUDIO_LID), CFG_FILE_SPEECH_REC_SIZE,
        CFG_FILE_SPEECH_REC_TOTAL, SIGNLE_DEFUALT_REC, (char *)&speech_custom_default, DataReset, NULL
    },
    // ...
};
```

### 步骤 4：逐项比对

按枚举顺序逐项比对数组中的 LID，检查以下三项：

| 检查项 | 说明 |
|--------|------|
| **一一对应** | 枚举中每个 LID 在数组中都有对应条目，数组中每个 LID 在枚举中也存在 |
| **顺序一致** | 数组中的 LID 顺序与枚举中完全一致 |
| **无缺漏** | 枚举条目数 = 数组条目数（不含 `MAX_LID` 终止符） |

### 步骤 5：输出结果

以表格形式输出每对对应关系及状态，最后给出结论。

## 输出模板

```
| # | Custom_NvRam_LID.h 枚举 | CFG_file_info_custom.h 数组 | 状态 |
|---|---|---|---|
| 1 | AP_CFG_xxx_LID | /mnt/vendor/nvdata/xxx | ✅ |
| ... | ... | ... | ... |

## 检查结论

| 检查项 | 结果 |
|--------|------|
| 枚举 LID 数量 | N 个（不含 MAX_LID） |
| 数组条目数量 | N 个 |
| 一一对应 | ✅/❌ |
| 顺序一致性 | ✅/❌ |
| 缺漏 | ✅/❌ |
```

## 注意事项

1. **`AP_CFG_CUSTOM_FILE_MAX_LID`** 是枚举终止符，不需要在数组中有对应条目
2. **`AP_CFG_RDCL_FILE_AUDIO_LID`** 是第一个有效 LID（被赋值为 `AP_CFG_CUSTOM_BEGIN_LID`）
3. 检查时需排除被注释掉的 LID（如 `AP_CFG_RDCL_FILE_META_LID`、`AP_CFG_CUSTOM_FILE_CUSTOM1_LID` 等灰色注释项），注释掉的 LID 在枚举和数组中应同时缺失
4. 如果发现缺失，**只报告具体缺失了什么**，明确列出缺失的 LID 名称、位于枚举的哪个位置、或数组缺少了哪条记录。**不要自动修改文件**，由用户自行决定如何处理

## 自检规则

每次执行完检查后，AI 必须逐项自检以下 4 点：

1. **是否完成了用户要求的任务** — 是否检查了正确的项目路径
2. **枚举和数组是否逐项完整比对** — 确认无跳行、无遗漏
3. **是否存在不确定的内容** — 如有无法确定的内容，明确写出"不确定"并说明原因
4. **最终结论是否明确** — 明确输出"通过"或"不通过"，并说明具体问题
