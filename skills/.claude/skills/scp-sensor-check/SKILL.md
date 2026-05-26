---
name: "scp-sensor-check"
description: "全面检查 MTK SCP 项目 sensor 配置是否正确生效。验证 project.mk 宏定义与 sensorhub.mk、platform.mk、DTS、库文件的关联完整性。当用户要求检查某项目 sensor 配置、验证 NV/sensor 宏是否生效、排查 sensor 功能缺失时调用。"
funcType: "AI自动化适配"
category: "驱动"
---

# SCP Sensor 配置验证

对 MTK tinysys SCP 项目执行系统性的 sensor 配置生效验证，确保 project.mk 中所有 sensor 相关宏正确关联到驱动实现、DTS 配置、算法库。

## 适用场景

用户要求对某个 SCP 项目进行 sensor 配置检查时调用。典型触发语：
- "检查 xxx 项目的 sensor 配置是否生效"
- "验证 project.mk 中 sensor 宏"
- "排查 sensor 功能缺失问题"
- "帮我看看 sensor 配置有没有遗漏"

## 构建系统宏传递机制

以下流程适用于所有 MTK SCP 项目：

```
Makefile (顶层)
  └─ build/main.mk → build/config.mk
       ├─ rvxx.mk        ← 最先加载，定义 RVXX_LIB 等架构参数
       ├─ platform.mk    ← 定义所有 CFG_ 宏默认值
       │    ├─ -include project.mk   ← 项目级覆盖（后加载，覆盖前者）
       │    ├─ if CFG_SENSORHUB_SUPPORT=yes → include sensorhub.mk
       │    │    └─ 所有 sensor 驱动的 ifeq 条件编译/链接块
       │    └─ if CFG_CHRE_SUPPORT=yes     → include chre.mk
       │         └─ 可能包含部分传感器虚拟驱动（stationary/glance/pickup）
       └─ tinysys_config.h ← platform.mk + project.mk 所有 CFG_ 宏 → #define
            └─ -include 注入所有 .c 文件编译
```

**加载顺序**（关键）：
1. rvxx.mk （config.mk L4）
2. platform.mk （config.mk L164）
3. project.mk （platform.mk L212，`-include`，后者覆盖前者）
4. sensorhub.mk / chre.mk （platform.mk 内条件引入）

**两种生效方式**：
1. **构建系统级** (`ifeq`): 在 sensorhub.mk / chre.mk 中通过 `ifeq ($(CFG_XXX),yes)` 控制文件编译和库链接
2. **源码级** (`#ifdef`): 通过 tinysys_config.h 的 `#define CFG_XXX` 注入 C 源码。**但仅当 #ifdef 所在的 .c 文件被编译时才真正生效**（见步骤 5）

## 检查步骤

### 步骤 1：确定项目路径参数

从用户输入或上下文中获取：

| 参数 | 含义 | 示例 |
|------|------|------|
| PROCESSOR | 处理器架构 | RV55_A / RV33_A |
| PLATFORM | 芯片平台 | mt6789 / mt6895 / mt6858 |
| PROJECT | 项目名 | lj6_h897 / x6895_h8925 |
| SCP_DIR | SCP 根目录 | 通常 `vendor/mediatek/proprietary/tinysys/scp` |

构建关键路径：
- `PROJECT_DIR = {SCP_DIR}/project/{PROCESSOR}/{PLATFORM}/{PROJECT}`
- `PLATFORM_DIR = {SCP_DIR}/project/{PROCESSOR}/{PLATFORM}/platform`
- `PROJECT_MK = {PROJECT_DIR}/project.mk`
- `PLATFORM_MK = {PLATFORM_DIR}/platform.mk`
- `RVXX_MK = {PLATFORM_DIR}/rvxx.mk`
- `SENSORHUB_MK = {PLATFORM_DIR}/features/sensorhub.mk`
- `CHRE_MK = {PLATFORM_DIR}/features/chre.mk`
- `DTS_C = {PROJECT_DIR}/sensor/dts.c`
- `OVERLAY_H = {PROJECT_DIR}/inc/overlay_sensor.h`

读取所有上述文件以获取完整上下文。

### 步骤 2：提取 project.mk 中全部 sensor 宏

逐行分析 `project.mk` 的 sensor 配置段（通常以 `####### sensor config start #######` 标注），提取所有 `CFG_` 开头的宏，按以下分类记录：

1. **Feature 功能宏**: `CFG_SENSORHUB_SUPPORT`、`CFG_ACCGYRO_SUPPORT`、`CFG_ALSPS_SUPPORT`、`CFG_MAGNETOMETER_SUPPORT`、`CFG_FUSION_SUPPORT` 等
2. **器件型号宏**: `CFG_ICM4N607_SUPPORT`、`CFG_MMC5603_SUPPORT`、`CFG_MN78911_SUPPORT`、`CFG_LSM6DSO_SUPPORT` 等
3. **虚拟传感器宏**: `CFG_STEP_COUNTER_SUPPORT`、`CFG_TILT_SUPPORT`、`CFG_MOTION_SUPPORT`、`CFG_ANTI_TOUCH_SUPPORT`、`CFG_ELEVATOR_DETECT_SUPPORT`、`CFG_STATIONARY_SUPPORT`、`CFG_TRANS_WAKEUP_SUPPORT`、`CFG_HEAD_POSTURE_SUPPORT`、`CFG_MSC_SUPPORT` 等
4. **系统配置宏**: `CFG_MAG_PROJECT_NAME`、`CFG_SENSOR_BROADCAST_DEPUTY_TASK`、`CFG_SENSORS_CTRL_SINGLEDATA_NUM`、`CFG_SENSORS_INDRAM`、`CFG_MAG_CALIBRATION_IN_AP` 等
5. **禁用宏**: 值为 `no` 的也记录，用于完整性对比

### 步骤 3：语法验证

- 所有宏使用 `CFG_XXX = value` 格式（等号两侧空格可有可无）
- 布尔值统一为 `yes` / `no`，不应出现 `true` / `false`
- 无拼写错误（交叉对比 platform.mk 和 sensorhub.mk 中的宏名）
- 无重复定义（同一宏在 project.mk 中出现两次）

### 步骤 4：platform.mk 覆盖关系

在 platform.mk 中搜索所有与 project.mk 同名的 CFG_ 宏，对比值：
- 值不同 → 确认 project.mk 的值是最终有效值（后加载覆盖）
- platform.mk 中不存在 → 标记为「项目新增宏」

特别关注：**`CFG_SENSORHUB_SUPPORT` 通常由 platform.mk 默认为 `no`，必须由 project.mk 覆盖为 `yes`**，否则整个 sensorhub 模块不被引入。

### 步骤 5：逐宏验证驱动实现关联（核心步骤）

对 project.mk 中每个 `= yes` 的宏，按以下**四层递进验证**：

```
Layer 1: sensorhub.mk 中搜索 ifeq ($(CFG_XXX),yes)
    ├── 找到 → ✅ 构建级生效，记录编译文件和链接库，结束
    └── 未找到 → 进入 Layer 2

Layer 2: chre.mk 中搜索 ifeq ($(CFG_XXX),yes)
    ├── 找到 → 检查 CFG_CHRE_SUPPORT 值
    │   ├── CHRE_SUPPORT = yes → ✅ 构建级生效（CHRE 路径）
    │   └── CHRE_SUPPORT = no  → 🟡 CHRE 未启用，进入 Layer 3
    └── 未找到 → 进入 Layer 3

Layer 3: 在 middleware/sensorhub 和 drivers 目录下搜索 #ifdef CFG_XXX
    ├── 找到 → 进入 Layer 4（交叉验证）
    │    └── 记录 #ifdef 所在的每个 .c 文件路径
    └── 未找到 → 🔴 完全未生效（死宏）

Layer 4: 交叉验证 #ifdef 所在文件是否被编译
    对 Layer 3 找到的每个 .c 文件，在 sensorhub.mk 中搜索是否出现在 C_FILES 列表中
    ├── 至少一个 .c 文件在编译列表中 → ✅ 源码级生效
    └── 全部不在编译列表中 → 🔴 宏通过 #define 注入但所在文件未被编译
        典型场景：某宏的 #ifdef 只在 tl_xxx.c / sr_xxx.c 中，
        但实际编译的是 xxx.c（无该 #ifdef）
```

**判定结论**：

| 场景 | 结论 |
|------|------|
| sensorhub.mk 找到 | **构建级生效**（sensorhub 路径） |
| chre.mk 找到 + CHRE=yes | **构建级生效**（CHRE 路径） |
| chre.mk 找到 + CHRE=no + C源码找到且被编译 | **源码级生效** |
| chre.mk 找到 + CHRE=no + C源码找到但未被编译 | 🔴 **P1: #ifdef存在但所在文件未被编译** |
| chre.mk 找到 + CHRE=no + C源码未找到 | 🔴 **P1: 完全未生效** |
| 均未找到 + C源码找到且被编译 | **源码级生效** |
| 均未找到 + C源码找到但未被编译 | 🔴 **P1: #ifdef存在但所在文件未被编译** |
| 均未找到 + C源码未找到 | 🔴 **P1: 完全未生效（死宏）** |

### 步骤 6：DTS 配置完整性

分析 `sensor/dts.c` 中**所有 `#ifdef CFG_` 开头的块**（注意宏命名风格多样：`CFG_XXX_SUPPORT`、`CFG_XXX_YYYY` 等）：

1. **DTS 中有但 project.mk 未定义的宏** → 🔴 DTS 配置不会生效
2. **project.mk 中 = yes 但 DTS 中无对应 #ifdef 的宏** → 🟡 缺少 DTS 硬件参数配置
3. 检查物理传感器的硬件参数是否完整：bus_id、slave_addr、direction、eint_num

### 步骤 7：库文件依赖检查

分两部分：

**A. 项目专属静态库**（路径包含 `CFG_MAG_PROJECT_NAME`）：
```
{PROJECT_DIR}/msensor/{vendor}/*.a
{PROJECT_DIR}/sensorlib/alslib/*.a
{PROJECT_DIR}/ois/*.a
{PROJECT_DIR}/flicker/**/*.a
```
使用 Glob 检查文件是否存在。

**B. 算法库目录**（sensorhub.mk 中 `LIBFLAGS` 引用的 algo 库）：
- 从 `rvxx.mk` 中确认 `RVXX_LIB` 的值（注意不同平台值不同：`RV55_A` / `RV55NN_A` / `RV55_A_E300` / `RV55NN_A_E300`）
- ALGO_DIR 路径为 `{SCP_DIR}/middleware/sensorhub/algos/{RVXX_LIB}`
- 检查 sensorhub.mk 中所有 `-L$(ALGO_DIR)/xxx -lxxx` 对应的 `.a` 文件是否存在

### 步骤 8：辅助文件检查

- **opts.mk**: 检查是否存在（`-include` 引入，缺失不影响构建），如有则列出 sensor 相关配置
- **overlay_sensor.h**: 如存在，检查其中配置的传感器芯片名是否与 project.mk 实际启用的器件匹配。`CFG_OVERLAY_INIT_SUPPORT=no` 时无影响，但若将来启用需更新
- **single_data_ld.h**: 检查是否需要额外数据分区
- **cust_ois_param.h**: 若 `CFG_OIS_SUPPORT=yes` 则验证 OIS 参数

### 步骤 9：冲突检查

- platform.mk 与 project.mk 是否对同一宏设了矛盾值
- 互斥功能是否同时被设为 yes
- HEAP 分配是否正确响应 sensor 宏（platform.mk 中搜索 `TOTAL_HEAP_SIZE` 的 sensor 相关条件块）
- 检查 `CFG_SENSOR_BROADCAST_DEPUTY_TASK` 对 heap 的影响

## 输出格式

完成检查后按以下 9 段结构输出报告。可直接输出也可写入 `{SCP_DIR}/.trae/documents/{PROJECT}_sensor_check_report.md`：

```
## {PROJECT} ({PLATFORM}/{PROCESSOR}) SCP Sensor 配置验证报告

### 一、宏定义清单
| 分类 | 宏名 | 值 |

### 二、语法检查
| 检查项 | 结果 |

### 三、platform.mk 覆盖关系
| 宏名 | platform.mk | project.mk | 最终 | 状态 |

### 四、驱动实现关联验证
| 宏名(=yes) | 生效方式 | 位置/文件 | 结论 |
生效方式取值：构建级(sensorhub) / 构建级(CHRE) / 源码级(#ifdef+已编译) / 源码级(#ifdef+未编译) / 未生效

### 五、DTS 配置
| #ifdef宏 | project.mk值 | 状态 |

### 六、库文件依赖
| 文件路径 | 存在 | 对应宏 |

### 七、辅助配置
| 文件 | 状态 | 说明 |

### 八、问题汇总
| # | 级别 | 宏 | 问题 | 修复建议 | 优先级 |

### 九、整体评估
[总结 + 已生效功能数量 + 问题数量 + 建议]
```

## 问题级别定义

| 级别 | 标识 | 含义 | 修复优先级 |
|------|:---:|------|:---:|
| P1 | 🔴 | 宏设为 yes 但实际不生效，功能缺失 | 立即修复 |
| P2 | 🟡 | 宏设为 yes 但生效范围有限，或缺少对应配置 | 建议修复 |
| P3 | 🟢 | 信息提示，需确认意图 | 确认后处理 |

## 修复建议模板

| 问题类型 | 标准修复建议 |
|---------|-------------|
| 死宏（完全未生效） | 1. 确认是否需要在 sensorhub.mk 中添加 ifeq 块<br>2. 或确认宏是否应设为 no<br>3. 或检查是否使用了错误的宏名 |
| 源码级但文件未被编译 | 1. 确认 sensorhub.mk 中编译的 .c 文件是否正确<br>2. 或将 #ifdef 逻辑移植到实际编译的 .c 文件中<br>3. 或改用含该 #ifdef 的 .c 文件（如 tl_xxx.c → xxx.c) |
| CHRE 依赖未启用 | 1. 若需 CHRE 功能：project.mk 中添加 `CFG_CHRE_SUPPORT = yes`<br>2. 若不需 CHRE：在 sensorhub.mk 中添加独立驱动块，或接受当前限制 |
| DTS 有但宏未定义 | 1. project.mk 中添加对应宏定义<br>2. 或从 dts.c 中移除未使用的 #ifdef 块 |
| 缺少 DTS 配置 | 1. 在 dts.c 中添加对应传感器的 #ifdef 块和硬件参数 |
| overlay 配置不匹配 | 1. 更新 overlay_sensor.h 中传感器名称与实际使用一致 |
| 库文件缺失 | 1. 确认库文件是否应存在于项目目录<br>2. 或检查 `CFG_MAG_PROJECT_NAME` 路径是否正确 |

## 常见问题模式

以下是已验证到的高频问题模式，检查时需特别注意：

1. **宏在 project.mk = yes 但 sensorhub.mk 中无 ifeq 块** — 最常见问题。此类宏可能：
   - 仅在 chre.mk 中使用（但 CHRE_SUPPORT 通常 = no，导致实际不生效）
   - 仅通过 #ifdef 在 C 源码中生效（需进一步执行 Layer 4 交叉验证）
   - 完全没有被任何代码引用（死宏）

2. **#ifdef 所在 .c 文件与 sensorhub.mk 编译的 .c 文件不一致** — 同一类传感器存在多个驱动变体（如 `mn78xxx.c`、`tl_mn78xxx.c`、`sr_mn78xxx.c`），子特性宏的 #ifdef 可能只存在于某些变体中，但实际编译的是另一个。这是 Layer 4 要抓的典型问题。

3. **DTS 中有 #ifdef 但 project.mk 未定义该宏** — DTS 代码预留了但宏未启用

4. **overlay_sensor.h 中配置的传感器与实际使用完全不同** — overlay 启用时会编译错误驱动

5. **宏命名风格不统一** — 功能/器件使能用 `CFG_XXX_SUPPORT` 后缀；子特性/行为标志可能没有（如 `CFG_XXX_SEPARATE_SUPPORT`、`CFG_XXX_PS_CHK_SUN`）。project.mk 中的宏名必须与 sensorhub.mk 的 `ifeq` 和 C 源码中的 `#ifdef` 精确匹配。
