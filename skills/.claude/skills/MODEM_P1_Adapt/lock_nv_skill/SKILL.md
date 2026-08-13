# 锁卡NV修改子技能

## 基本信息
- **name**: 锁卡NV修改子技能
- **description**: 负责在目标分支公共仓中修改锁卡相关的NV参数配置。支持在sml_public_def.h、l4_nvram_def.h、l4_nvram_editor.h三个文件中添加指定BOM名称的宏控。
- **version**: 1.0.0
- **env**:
  - model: claude-3-5-sonnet
  - python_version: 3.11+
  - dependencies: []

## 技能定位
本技能是MODEM大版本升级的"工人"之一，负责执行锁卡NV参数的修改操作：
1. 直接接收主控技能传来的目标分支公共仓路径和BOM名称
2. 在指定的三个文件中搜索需要修改的宏控代码
3. 根据C语言编码规则添加锁卡NV宏控
4. 统计修改结果并返回给主控技能

## 输入参数
从主控技能接收以下参数：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| Path_B_Pub | string | 代码B（目标分支）的公共仓路径 |
| BOM_Name_Target | string | 变更后的BOM名称，用于添加宏控 |

## 执行流程
1. **验证输入参数**：检查Path_B_Pub是否有效
2. **修改sml_public_def.h**：在/mcu/interface/protocol/general/sml_public_def.h文件中添加宏控
   - 搜索10个目标宏定义
   - 在每个宏定义后的第一个#if宏控行末添加 `|| defined(__{BOM_Name_Target}__)`
3. **修改l4_nvram_def.h**：在/mcu/interface/service/nvram/l4_nvram_def.h文件中添加宏控
   - 搜索2个目标宏定义
   - 在每个宏定义后的第一个#if宏控行末添加 `|| defined(__{BOM_Name_Target}__)`
4. **修改l4_nvram_editor.h**：在/mcu/interface/service/nvram/l4_nvram_editor.h文件中添加宏控
   - 搜索3个目标宏定义
   - 在每个宏定义后的第一个#if宏控行末添加 `|| defined(__{BOM_Name_Target}__)`
5. **结果统计**：统计修改的文件数和修改位置
6. **返回结果**：将修改结果传递给主控技能

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
| `time_stamp:"[DOC, RUNTIME]Time stamp value in BLOB"` | 后续第一个#if宏控 |
| `code_cat_sp:"[DOC, RUNTIME]Service Provider Configuration code: MCC-MNC-GID triplets"` | 后续第一个#if宏控 |
| `signature:"[DOC, RUNTIME]Signature: Verification code used for blob validation"` | 后续第一个#if宏控 |

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