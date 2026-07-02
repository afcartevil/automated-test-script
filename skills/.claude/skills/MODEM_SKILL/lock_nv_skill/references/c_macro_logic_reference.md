# 锁卡NV修改 - C语言宏控逻辑参考

## 概述
本参考文档详细说明锁卡NV修改子技能中涉及的C语言宏控逻辑，确保修改操作严格遵循C语言语法和编码规范。

## C语言宏定义基本规则

### 1. 宏定义语法
```c
#define MACRO_NAME value
#define MACRO_NAME(parameter_list) replacement_text
```

### 2. 条件编译指令
```c
#if defined(MACRO_NAME)
    // 代码块
#elif defined(OTHER_MACRO)
    // 代码块
#else
    // 代码块
#endif
```

### 3. 宏定义命名规范
- 宏名称通常使用大写字母
- 单词之间用下划线分隔
- 项目特定宏通常以项目代号前缀（如 `__ck7n_h894_a1_d__`）

---

## 锁卡NV宏控修改逻辑

### 修改模式说明
本技能采用**精准定位+追加宏控**的修改模式：

```
1. 搜索目标宏定义（如 #define SML_SL_BLOB_TIME_STAMP_SIZE 8）
2. 定位到该宏定义所在行
3. 向下查找，找到第一个以 #if defined( 开头的条件编译行
4. 在该行末尾追加 || defined(__{BOM_Name_Target}__)
```

### 示例修改过程

**原始代码：**
```c
#define SML_SL_BLOB_TIME_STAMP_SIZE             8
//TDD:add for jio nv preset by yuqi.zhu5 20240529 start
//TDD: modify for X6731B modem bringup X6731BUH-4 by youjin.sun 20240613 start
//TDD: modify clat_v modem bringup AD10UH83-7 by xiaochao.wang 20250110 start
#if defined(__ck7n_h894_a1_d__) || defined( __lh7n_h894_o1__) || defined( __x1101b_m1101_a1__)
```

**修改后代码（假设 BOM_Name_Target = x6850b_h895_aa1_v）：**
```c
#define SML_SL_BLOB_TIME_STAMP_SIZE             8
//TDD:add for jio nv preset by yuqi.zhu5 20240529 start
//TDD: modify for X6731B modem bringup X6731BUH-4 by youjin.sun 20240613 start
//TDD: modify clat_v modem bringup AD10UH83-7 by xiaochao.wang 20250110 start
#if defined(__ck7n_h894_a1_d__) || defined( __lh7n_h894_o1__) || defined( __x1101b_m1101_a1__) || defined( __x6850b_h895_aa1_v__)
```

---

## 目标宏定义列表与修改规则

### sml_public_def.h 修改目标

| 序号 | 目标宏定义 | 修改规则 |
|------|-----------|---------|
| 1 | `#define SML_SL_BLOB_TIME_STAMP_SIZE             8` | 在后续第一个 #if defined( 行末追加 |
| 2 | `#define SML_SL_BLOB_LENGTH_SIZE                 2` | 在后续第一个 #if defined( 行末追加 |
| 3 | `#define SML_SL_BLOB_SIZE_OF_SIGNATURE           256` | 在后续第一个 #if defined( 行末追加 |
| 4 | `#define SML_SL_NVRAM_ACCESS_ID_UPDATE_LOCK_OP   0xFB` | 在后续第一个 #if defined( 行末追加 |
| 5 | `#define SML_SL_BLOB_SIZE_OF_CAT_SP     7` | 在后续第一个 #if defined( 行末追加 |
| 6 | `#define SML_SL_BLOB_MAX_SUPPORT_CAT_SP     10` | 在后续第一个 #if defined( 行末追加 |
| 7 | `#define SML_SL_BLOB_CAT_SP_SIZE         (SML_SL_BLOB_MAX_SUPPORT_CAT_SP * SML_SL_BLOB_SIZE_OF_CAT_SP)` | 在后续第一个 #if defined( 行末追加 |
| 8 | `kal_uint8   time_stamp[SML_SL_BLOB_TIME_STAMP_SIZE];` | 在后续第一个 #if defined( 行末追加 |
| 9 | `kal_uint8   code_cat_sp[SML_SL_BLOB_CAT_SP_SIZE];` | 在后续第一个 #if defined( 行末追加 |
| 10 | `kal_uint8   signature[SML_SL_BLOB_SIZE_OF_SIGNATURE];` | 在后续第一个 #if defined( 行末追加 |

### l4_nvram_def.h 修改目标

| 序号 | 目标宏定义 | 修改规则 |
|------|-----------|---------|
| 1 | `#define NVRAM_EF_SML_S_LID_VERNO    "001"` | 在后续第一个 #if defined( 行末追加 |
| 2 | `#define NVRAM_EF_SML_S_LID_HASH   0x4E0B7529` | 在后续第一个 #if defined( 行末追加 |

### l4_nvram_editor.h 修改目标

| 序号 | 目标宏定义 | 修改规则 |
|------|-----------|---------|
| 1 | `time_stamp:"[DOC, RUNTIME]Time stamp value in BLOB"` | 在后续第一个 #if defined( 行末追加 |
| 2 | `code_cat_sp:"[DOC, RUNTIME]Service Provider Configuration code: MCC-MNC-GID triplets"` | 在后续第一个 #if defined( 行末追加 |
| 3 | `signature:"[DOC, RUNTIME]Signature: Verification code used for blob validation"` | 在后续第一个 #if defined( 行末追加 |

---

## C语言语法检查规则

### 0. 注释识别与过滤（重要）
在进行宏控修改时，必须严格区分代码和注释，确保宏控不会被错误地添加到注释中。

#### C语言注释类型
```c
// 单行注释（从 // 开始到行末）
/* 多行注释（从 /* 开始到 */ 结束，可以跨多行） */
```

#### 注释过滤规则
1. **跳过纯注释行**：以 `//` 或 `/*` 开头的行应跳过
2. **跳过注释中的内容**：在搜索条件编译指令时，忽略 `//` 后的所有内容
3. **处理行内注释**：如果 `#if defined(` 行末尾有 `//` 注释，宏控应添加在注释之前

#### 正确与错误示例

**错误情况：**
```c
#if defined(__ck7n_h894_a1_d__) // some comment || defined(__new_macro__)
// 宏控错误地加到了注释后面
```

**正确情况：**
```c
#if defined(__ck7n_h894_a1_d__) || defined(__new_macro__) // some comment
// 宏控正确地添加在注释之前
```

#### 注释处理流程图
```
输入行: #if defined(__xxx__) || defined(__yyy__) // this is a comment
            ↓
    检测是否包含 //
            ↓
    提取 // 之前的内容
            ↓
    在提取的内容末尾添加宏控
            ↓
    重新拼接：新内容 + // + 原注释
            ↓
    结果: #if defined(__xxx__) || defined(__yyy__) || defined(__new__) // this is a comment
```

### 1. 宏定义语法验证
```c
// 有效宏定义格式
#define MACRO_NAME value
#define MACRO_NAME (value)
#define MACRO_NAME "string"
#define MACRO_NAME 0x1234

// 无效格式（应跳过）
#define MACRO_NAME    // 无值
#undef MACRO_NAME     // 取消定义
#define              // 不完整
```

### 2. 条件编译指令识别
```c
// 有效的条件编译起始行
#if defined(MACRO)
#if !defined(MACRO)
#if defined(MACRO1) || defined(MACRO2)
#if defined(MACRO1) && defined(MACRO2)

// 应跳过的行
#ifdef MACRO           // 使用 #if defined() 格式而非 #ifdef
#ifndef MACRO          // 使用 #if !defined() 格式而非 #ifndef
#if 0                  // 常量表达式，不是宏控
```

### 3. 追加宏控格式
```c
// 正确格式（追加在条件编译行末尾）
#if defined(__existing_macro__) || defined(__new_macro__)

// 错误格式
#if defined(__existing_macro__) || defined(__new_macro__)    // 末尾无多余空格
// 注意：添加时应保留原行格式，只在末尾添加 || defined(__{BOM_Name_Target}__)
```

---

## 边界情况处理

### 1. 目标宏定义未找到
- **处理策略**：跳过该宏定义，记录警告信息
- **日志记录**："未找到目标宏定义: {macro_text}"

### 2. 后续无#if defined( 指令
- **处理策略**：跳过该宏定义，记录警告信息
- **日志记录**："宏定义 {macro_text} 后未找到条件编译指令"

### 3. 目标文件不存在
- **处理策略**：跳过该文件，记录错误信息
- **日志记录**："文件不存在: {file_path}"

### 4. 文件已包含目标宏控
- **处理策略**：跳过该修改点，记录信息
- **日志记录**："目标宏控已存在: __{BOM_Name_Target}__"

### 5. 代码行过长
- **处理策略**：C语言标准允许任意长度的行，直接在末尾追加
- **注意**：某些编译器可能有行长度限制（通常 >= 4096字符）

---

## 修改顺序与依赖关系

### 修改顺序
1. sml_public_def.h（10处）
2. l4_nvram_def.h（2处）
3. l4_nvram_editor.h（3处）

### 依赖关系
```
sml_public_def.h 定义锁卡NV相关的数据结构和常量
        ↓
l4_nvram_def.h 定义NV RAM数据存储的版本号和哈希值
        ↓
l4_nvram_editor.h 定义NV编辑器中锁卡相关字段的元数据
```

---

## 代码审查检查点

### 检查清单
- [ ] 所有修改都在正确的文件中
- [ ] 所有修改都在正确的位置（目标宏定义后的第一个#if defined行）
- [ ] 宏控格式正确（`|| defined(__{BOM_Name_Target}__)`）
- [ ] 没有修改其他无关代码
- [ ] 保留了原有的注释和代码风格
- [ ] 修改后代码可以通过C语言编译器语法检查

### 验证命令
```bash
# 检查C语法（需要安装gcc或clang）
gcc -fsyntax-only mcu/interface/protocol/general/sml_public_def.h
gcc -fsyntax-only mcu/interface/service/nvram/l4_nvram_def.h
gcc -fsyntax-only mcu/interface/service/nvram/l4_nvram_editor.h

# 搜索验证（确认修改已生效）
grep "__{BOM_Name_Target}__" mcu/interface/protocol/general/sml_public_def.h
grep "__{BOM_Name_Target}__" mcu/interface/service/nvram/l4_nvram_def.h
grep "__{BOM_Name_Target}__" mcu/interface/service/nvram/l4_nvram_editor.h
```

---

## 安全注意事项

### 1. 文件备份
修改前应自动备份原始文件：
```bash
cp sml_public_def.h sml_public_def.h.backup
```

### 2. 权限检查
确保有文件写入权限：
```bash
# 检查文件是否可写
test -w sml_public_def.h && echo "可写" || echo "不可写"
```

### 3. 事务性修改
如果多个文件需要修改，应确保要么全部成功，要么全部回滚：
```bash
# 伪代码逻辑
begin_transaction()
try:
    modify_file(sml_public_def.h)
    modify_file(l4_nvram_def.h)
    modify_file(l4_nvram_editor.h)
    commit_transaction()
except:
    rollback_transaction()
    restore_backups()
```

---

## 示例完整修改流程

### 输入参数
- Path_B_Pub: `/path/to/target/public`
- BOM_Name_Target: `x6850b_h895_aa1_v`

### 修改步骤

**步骤1: 修改 sml_public_def.h**
```bash
# 定位文件
file_path="${Path_B_Pub}/mcu/interface/protocol/general/sml_public_def.h"

# 备份文件
cp "${file_path}" "${file_path}.backup"

# 修改第1处
# 搜索: #define SML_SL_BLOB_TIME_STAMP_SIZE             8
# 在后续第一个#if defined(行末添加: || defined(__x6850b_h895_aa1_v__)

# 修改第2处
# 搜索: #define SML_SL_BLOB_LENGTH_SIZE                 2
# 在后续第一个#if defined(行末添加: || defined(__x6850b_h895_aa1_v__)

# ... 依次修改剩余8处
```

**步骤2: 修改 l4_nvram_def.h**
```bash
file_path="${Path_B_Pub}/mcu/interface/service/nvram/l4_nvram_def.h"
cp "${file_path}" "${file_path}.backup"

# 修改第1处
# 搜索: #define NVRAM_EF_SML_S_LID_VERNO    "001"
# 在后续第一个#if defined(行末添加: || defined(__x6850b_h895_aa1_v__)

# 修改第2处
# 搜索: #define NVRAM_EF_SML_S_LID_HASH   0x4E0B7529
# 在后续第一个#if defined(行末添加: || defined(__x6850b_h895_aa1_v__)
```

**步骤3: 修改 l4_nvram_editor.h**
```bash
file_path="${Path_B_Pub}/mcu/interface/service/nvram/l4_nvram_editor.h"
cp "${file_path}" "${file_path}.backup"

# 修改第1处
# 搜索: time_stamp:"[DOC, RUNTIME]Time stamp value in BLOB"
# 在后续第一个#if defined(行末添加: || defined(__x6850b_h895_aa1_v__)

# ... 依次修改剩余2处
```

**步骤4: 验证修改**
```bash
# 验证语法
gcc -fsyntax-only "${Path_B_Pub}/mcu/interface/protocol/general/sml_public_def.h"
gcc -fsyntax-only "${Path_B_Pub}/mcu/interface/service/nvram/l4_nvram_def.h"
gcc -fsyntax-only "${Path_B_Pub}/mcu/interface/service/nvram/l4_nvram_editor.h"

# 统计修改数量
count=$(grep -c "__x6850b_h895_aa1_v__" "${Path_B_Pub}/mcu/interface/protocol/general/sml_public_def.h" \
    "${Path_B_Pub}/mcu/interface/service/nvram/l4_nvram_def.h" \
    "${Path_B_Pub}/mcu/interface/service/nvram/l4_nvram_editor.h")
echo "共修改 ${count} 处"
```

---

## 错误处理与恢复

### 错误类型与处理方式

| 错误类型 | 处理方式 | 恢复策略 |
|---------|---------|---------|
| 文件不存在 | 跳过该文件，记录错误 | 无 |
| 权限不足 | 提示用户检查权限 | 手动修改权限后重试 |
| 语法错误 | 回滚修改，恢复备份 | 恢复 .backup 文件 |
| 修改失败 | 记录详细错误信息 | 手动检查并修复 |

### 恢复命令
```bash
# 恢复所有备份文件
cp sml_public_def.h.backup sml_public_def.h
cp l4_nvram_def.h.backup l4_nvram_def.h
cp l4_nvram_editor.h.backup l4_nvram_editor.h
```