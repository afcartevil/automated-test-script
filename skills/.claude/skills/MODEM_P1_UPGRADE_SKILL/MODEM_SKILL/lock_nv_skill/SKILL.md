---
name: lock-nv-skill
description: 负责在目标分支公共仓中修改锁卡相关的NV参数配置。自动检测 NVRAM_EF_SUBSIDY_LOCK_LID_VERNO 值，仅当值不为 "001" 时才执行修改。在sml_public_def.h、l4_nvram_def.h、l4_nvram_editor.h三个文件中添加指定BOM名称的宏控。修改必须使用 scripts/LockNvModify.ps1 脚本执行，禁止自行修改。当用户提到 "锁卡 NV"、"NV 修改" 时触发。
version: 2.0.0
tools: Read, Bash
---

# 锁卡NV修改子技能

## 技能定位
本技能是MODEM大版本升级的"工人"之一，负责执行锁卡NV参数的修改操作：
1. 直接接收主控技能传来的目标分支公共仓路径和BOM名称
2. 自动检测 NVRAM_EF_SUBSIDY_LOCK_LID_VERNO 的值，判断是否需要修改
3. 如需修改，通过脚本在3个文件的15处固定位置添加宏控
4. 统计修改结果并返回给主控技能

## 输入参数
从主控技能接收以下参数：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Path_B_Pub | string | 代码B（目标分支）的公共仓路径 |
| BOM_Name_Target | string | 变更后的BOM名称，用于添加宏控 |

## 执行流程
1. **验证输入参数**：检查Path_B_Pub是否有效
2. **自动判断是否需要修改**（脚本内部执行）：
   - 检查 `/mcu/interface/service/nvram/l4_nvram_def.h` 中 `NVRAM_EF_SUBSIDY_LOCK_LID_VERNO` 的值
   - 如果值为 `"001"` → 直接跳过，返回"无需修改"
   - 如果值不为 `"001"` → 继续执行修改
3. **执行修改**（使用 `scripts/LockNvModify.ps1`）：
   - 修改 sml_public_def.h（10处）
   - 修改 l4_nvram_def.h（2处）
   - 修改 l4_nvram_editor.h（3处）
   - 每处修改在目标宏定义后的第一个 `#if defined(...)` 行末添加 `|| defined(__{BOM_Name_Target}__)`
4. **结果统计**：解析脚本JSON输出，统计修改/跳过的文件数和位置
5. **返回结果**：将修改结果传递给主控技能

## 硬约束（必须遵守）
1. **修改只能用脚本**：必须通过 `scripts/LockNvModify.ps1` 执行。**禁止**自行构造 Edit、Grep 或其他搜索/修改命令
2. **不读取脚本内容**：直接执行脚本即可，不需要阅读脚本源码
3. **不询问用户是否执行**：脚本会自动判断是否需要修改，无需人工确认
4. **NVRAM_EF_SUBSIDY_LOCK_LID_VERNO 为 "001" 时**：直接跳过，说明当前项目不需要锁卡NV修改

## 修改目标列表

### sml_public_def.h（10处修改）
| 目标宏定义 | 修改位置 |
|-----------|---------|
| `#define SML_SL_BLOB_TIME_STAMP_SIZE             8` | 后续第一个#if宏控 |
| `#define SML_SL_BLOB_LENGTH_SIZE                 2` | 后续第一个#if宏控 |
| `#define SML_SL_BLOB_SIZE_OF_SIGNATURE           256` | 后续第一个#if宏控 |
| `#define SML_SL_NVRAM_ACCESS_ID_UPDATE_LOCK_OP   0xFB` | 后续第一个#if宏控 |
| `#define SML_SL_BLOB_SIZE_OF_CAT_SP     7` | 后续第一个#if宏控 |
| `#define SML_SL_BLOB_MAX_SUPPORT_CAT_SP     10` | 后续第一个#if宏控 |
| `#define SML_SL_BLOB_CAT_SP_SIZE         (SML_SL_BLOB_MAX_SUPPORT_CAT_SP * SML_SL_BLOB_SIZE_OF_CAT_SP)` | 后续第一个#if宏控 |
| `kal_uint8   time_stamp[SML_SL_BLOB_TIME_STAMP_SIZE];` | 后续第一个#if宏控 |
| `kal_uint8   code_cat_sp[SML_SL_BLOB_CAT_SP_SIZE];` | 后续第一个#if宏控 |
| `kal_uint8   signature[SML_SL_BLOB_SIZE_OF_SIGNATURE];` | 后续第一个#if宏控 |

### l4_nvram_def.h（2处修改）
| 目标宏定义 | 修改位置 |
|-----------|---------|
| `#define NVRAM_EF_SML_S_LID_VERNO    "001"` | 后续第一个#if宏控 |
| `#define NVRAM_EF_SML_S_LID_HASH   0x4E0B7529` | 后续第一个#if宏控 |

### l4_nvram_editor.h（3处修改）
| 目标宏定义 | 修改位置 |
|-----------|---------|
| `time_stamp:"[DOC, RUNTIME]Time stamp value in BOM"` | 后续第一个#if宏控 |
| `code_cat_sp:"[DOC, RUNTIME]Service Provider Configuration code: MCC-MNC-GID triplets"` | 后续第一个#if宏控 |
| `signature:"[DOC, RUNTIME]Signature: Verification code used for blob validation"` | 后续第一个#if宏控 |

## 输出结果
| 输出项 | 类型 | 说明 |
|--------|------|------|
| success | boolean | 修改是否成功 |
| message | string | 执行结果描述 |
| skipped | boolean | 是否跳过（NVRAM_EF_SUBSIDY_LOCK_LID_VERNO="001"时为true） |
| subsidyLockLidVerno | string | NVRAM_EF_SUBSIDY_LOCK_LID_VERNO 的实际值 |
| modified_files | integer | 修改的文件数量 |
| modified_locations | integer | 修改的代码位置数量 |
| details | array | 修改详情列表 |
