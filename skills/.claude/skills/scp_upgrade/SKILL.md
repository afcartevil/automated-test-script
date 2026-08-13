---
name: "scp-upgrade"
description: "MTK Sensorhub 3.0 SCP code upgrade from OLD project to new baseline. ⚠️ MANDATORY: MUST ask user for confirmation before each step, NEVER proceed without user input. Invoke when upgrading SCP config or migrating sensor configurations between projects."
funcType: "AI自动化适配"
category: "驱动"
---

# MTK Sensorhub 3.0 SCP 升级调试

## ⛔ 强制执行规则（MUST READ FIRST）

**🚨 这些规则优先级最高，违反任何一条都将导致任务失败：**

### 规则 1：必须先询问，禁止自行假设
- ❌ **FORBIDDEN**: 不要假设旧项目路径、新基线路径、sensor 列表、新增 feature 等任何信息
- ✅ **REQUIRED**: 每个步骤开始前，必须先向用户询问并获取确认
- 🛑 **STOP**: 如果用户未提供必要信息，立即停止并询问，不要猜测或使用默认值

### 规则 2：以旧项目为准，以用户文档为参考
- 所有配置必须从**旧项目源文件**中读取
- 飞书文档仅作为**参考教程**，不作为配置来源
- 如果旧项目配置与文档示例不同，**以旧项目为准**

### 规则 3：流程门控（Flow Gates）
- 每个步骤完成后，**必须等待用户确认**才能进入下一步
- 用户有权在任何时候修改、拒绝或补充信息
- **不要批量执行多个步骤**，严格按顺序逐一进行

## 参考文档

**重要**：以用户提供的飞书文档作为主要参考教程：
- [AI]底软集成sensor3.0 MTK平台P1-整体：https://transsioner.feishu.cn/wiki/DE6YwDyguirlqckJc2TcKxu7nCg
- [AI]底软集成sensor3.0 MTK平台P1-/vendor/mediatek/proprietary/tinysys/scp：https://transsioner.feishu.cn/wiki/O08mwTLjWitFAikTR3zcwdHZnTd
- 底软集成sensor3.0 MTK平台P1：https://transsioner.feishu.cn/wiki/V7Etwk5lRiMbFCkWCl0cBxcsnRg

## 概述

本 Skill 用于协助完成 MTK Sensorhub 3.0 平台的 SCP 代码升级任务，将旧项目的配置迁移到新基线。

"旧项目" 指升级前的 SCP 项目目录，通常位于 `<旧基线>/vendor/mediatek/proprietary/tinysys/scp/project/{RV55_A|RV33_A}/{平台}/{项目名}/`。步骤1中用户提供的 "旧项目路径" 即指此 SCP 项目目录的完整路径。

## 核心原则

1. **以飞书文档为主要参考教程**
2. **新增 Feature 必须由用户提供**：升级后项目的新 feature 需要额外添加，禁止自行猜测
3. **业务规则优先**：重要业务规则（OIS、抬手亮屏、Significant Motion 等）优先于一般配置规则
4. **"以旧项目为准"≠全部照搬**：不同文件的处理原则不同，详见各步骤说明

## 重要业务规则（从实践中总结）

### 1. 抬手亮屏算法选择规则
- **MTK 抬手亮屏**：`CFG_WAKEUP_SUPPORT` - 新项目统一关闭，只使用自研算法
- **自研抬手亮屏**：`CFG_TRANS_WAKEUP_SUPPORT` - 新项目统一使用此配置
- **规则**：新项目统一只用自研算法，`CFG_WAKEUP_SUPPORT = no`，`CFG_TRANS_WAKEUP_SUPPORT = yes`

### 2. Flicker 传感器说明
- Flicker 是**单独的物理 sensor**，不是虚拟传感器
- 如果旧项目没有配置 Flicker，说明项目不需要此功能
- 后续如果需要添加 Flicker 支持，需要：
  1. 在 project.mk 中添加 `CFG_STK31860_ALSFLICKER = yes`
  2. 在 dts.c 中添加相应的 Flicker sensor 配置

### 3. OIS（光学防抖）配置规则
- **OIS 不由 sensor 负责**：新项目中 OIS 功能不再由 sensor 模块管理
- **处理方式**：OIS 相关内容**不需要修改**，保持新项目原有的配置即可
- **注意**：旧项目中的 OIS 配置（如 `CFG_OIS_SUPPORT`、`lsm6dsvq_ois`、`dw9828` 等）不需要同步到新项目

### 4. Significant Motion（重要动作检测）配置规则
- **必须配置**：`CFG_SIGNIFICANT_MOTION_SUPPORT = yes`，所有新项目都需要开启
- **处理方式**：升级完成后**必须检查** project.mk 中是否配置了此宏，如果未配置则补上 `CFG_SIGNIFICANT_MOTION_SUPPORT = yes`

### 5. 电梯模式（Elevator Detect）规则
- **新项目默认都加电梯模式**：`CFG_ELEVATOR_DETECT_SUPPORT = yes`
- 旧项目没有也要补上

### 6. CFG_SENSORS_INDRAM 规则
- **新项目默认 `CFG_SENSORS_INDRAM = yes`**，这是新基线的系统级配置
- **不要**因为旧项目是 `no` 而改动，保持新基线默认值

### 7. 宏名变化需深入验证
当新旧分支中对同一功能使用不同宏名时（如 `CFG_ANTI_TOUCH_SUPPORT` vs `CFG_ANTI_TOUCH_ULTRASOUND_SUPPORT`），**必须搜索 sensorhub.mk 和 C 源码**来判断是否为同一功能的不同实现方案，不可凭经验猜测。

### 8. 驱动专属宏联动删除规则
当删除一个芯片的 support 宏时，**必须同时检查并删除其所有附属宏**。例如：
- 删除 STK33562 系列 → 同时删除 `CFG_STK33562_CHANNEL_ALS`、`CFG_STK33562_ALS_SWITCH_GAIN`
- 删除 QMC6308 → 同时删除 dts.c 中的对应段
- **检查方法**：project.mk 修改完成后，逐行扫描所有 `CFG_` 宏，对任何不确定归属的宏向用户确认

### 9. 文件复制/删除方法（网络映射盘环境）
在 Windows 网络映射盘环境下操作文件时：
- ❌ 避免使用：`xcopy`、`cp`、`robocopy`（会遇到文件属性修改错误）
- ✅ 推荐：PowerShell 的 `New-Item` + `Copy-Item` 逐个文件操作
- **删除文件**：先用 `DeleteFile` 工具删文件，空目录可用 `Remove-Item -Force`（可能报错但文件已删）；网络盘上空目录删不掉不影响编译

---

## 升级流程

---

### 🛑 步骤 1：检索旧项目配置 [需要用户输入]

#### ⚠️ 执行前置条件（REQUIRED）
**在开始此步骤之前，必须先从用户处获取以下信息：**
- [ ] 旧项目的完整路径
- [ ] 新基线的完整路径
- [ ] 项目名称/代号（如 CLx、ODxx、LJxx、Xxxx等）

**如果用户未提供上述任何一项信息，立即停止并询问用户！不要猜测路径！**

#### 操作
从旧项目读取以下文件：
- `project.mk` - 项目宏配置
- `dts.c` - 传感器设备树配置
- `cache_ld.h` - DRAM Cache 配置
- `msensor/` 目录 - 传感器算法库

**注意**：这些文件通常位于 `project/{RV55_A|RV33_A}/{平台}/{项目名}/` 目录下

**同时读取新项目对应文件**，在对比中标注差异，方便后续修改。

#### 输出
分析并输出旧项目所配置的 sensor 列表，包括：
- 支持的 hardware sensor（加速度、陀螺仪、光感、地磁等）
- 支持的 virtual sensor（电梯检测、乘车检测、游戏虚拟操控等）
- DRAM 配置情况
- **新旧项目关键差异预览**（ALS芯片型号、地磁芯片、新增feature等）

#### ✅ 确认门控（CONFIRMATION GATE）
**🔴 必须等待用户确认以下内容后才能继续：**
- [ ] 用户确认旧项目 sensor 列表是否正确
- [ ] 用户确认是否有遗漏或错误
- [ ] 用户明确表示"可以继续下一步"

**如果用户提出修改意见，根据用户反馈重新分析，直到用户满意为止。**

---

### 🛑 步骤 2：询问新增 Feature [需要用户输入]

#### ⚠️ 执行前置条件（REQUIRED）
**此步骤完全依赖用户提供信息，不得跳过或假设。**

#### 操作
向用户询问升级后的项目有哪些新增的 feature，例如：
- 电梯模式（CFG_ELEVATOR_DETECT_SUPPORT）
- 乘车检测（CFG_VEHICLE_SUPPORT）
- 游戏虚拟操控（CFG_MSC_SUPPORT）
- SAR 检测（CFG_SAR_SUPPORT）
- Posture 姿态（CFG_POSTURE_SUPPORT）
- 其他新功能

**特别注意**：
- 新项目统一使用自研抬手亮屏（CFG_TRANS_WAKEUP_SUPPORT = yes），关闭 MTK 抬手亮屏（CFG_WAKEUP_SUPPORT = no），不需要询问
- 电梯模式（CFG_ELEVATOR_DETECT_SUPPORT）：**新代码默认都加**，不需要询问，直接告知用户
- Flicker 是单独的物理 sensor，旧项目没有配置则不需要添加

#### ✅ 确认门控（CONFIRMATION GATE）
**🔴 必须等待用户提供完整列表后才能继续：**
- [ ] 用户列出所有新增 feature
- [ ] 用户确认列表完整无遗漏

**❌ FORBIDDEN: 不要自己添加任何 feature，即使你认为某个功能"应该有"。**

---

### 🛑 步骤 3：配置 project.mk [依赖步骤1和2完成]

#### ⚠️ 执行前置条件（REQUIRED）
**确保已完成：**
- [x] 步骤1已通过用户确认
- [x] 步骤2已获取新增 feature 列表

#### 原则
1. **以旧项目的 sensor 配置为准**，复制的配置应与旧项目一致
2. 根据用户确认的新增 feature 添加对应的支持宏
3. **删除新基线中多余的配置**：新基线中有旧项目没有的 sensor 宏，删除（OIS 除外 → 规则见下一条）
4. **抬手亮屏**：新项目统一 `CFG_WAKEUP_SUPPORT = no`，`CFG_TRANS_WAKEUP_SUPPORT = yes`
5. **OIS 特殊处理**：新项目 OIS 不由 sensor 负责，OIS 相关配置**不需要修改**，保持新项目原有配置即可
6. **Significant Motion 检查**：必须检查 `CFG_SIGNIFICANT_MOTION_SUPPORT` 是否配置为 `yes`
7. **电梯模式**：新代码默认加，补上 `CFG_ELEVATOR_DETECT_SUPPORT = yes`
8. **CFG_SENSORS_INDRAM**：保持新基线默认 `yes`，不要因为旧项目是 `no` 而改动
9. **驱动专属宏联动删除**：删除芯片 support 宏时，同时删除其附属宏（如 STK33562 系列的 CHANNEL_ALS、ALS_SWITCH_GAIN）

#### 逐行审查步骤

完成 project.mk 修改后，执行以下审查：

1. 与旧项目逐行对比所有 `CFG_` sensor 宏，确认一致（OIS/INDRAM 除外）
2. 扫描新项目中所有旧项目没有的 `CFG_` 宏，逐一向用户确认是否需要保留
3. 检查是否有已删除芯片的附属宏残留

#### ✅ 完成确认
完成修改后，向用户展示修改摘要并等待确认。
**必须包含以下检查项：**
- [ ] `CFG_SIGNIFICANT_MOTION_SUPPORT = yes` 已配置
- [ ] `CFG_ELEVATOR_DETECT_SUPPORT = yes` 已配置
- [ ] `CFG_WAKEUP_SUPPORT = no`，`CFG_TRANS_WAKEUP_SUPPORT = yes`
- [ ] 已删除芯片无附属宏残留

---

### 🛑 步骤 4：配置 dts.c [依赖步骤1和2完成]

#### ⚠️ 执行前置条件（REQUIRED）
**确保已完成：**
- [x] 步骤1已通过用户确认
- [x] 步骤2已获取新增 feature 列表

#### 原则
- 以旧项目的 sensor 参数为准（direction、slave_addr、ps_threshold、eint_num 等）
- **删除新基线中多余的 sensor 段**：新基线中有旧项目没有的 sensor #ifdef 块，删除（OIS 除外）
- **注意参数一致性**：每个字段必须与旧项目完全一致
- **OIS 特殊处理**：OIS 相关配置**不需要修改**，保持新项目原有配置即可

#### ✅ 完成确认
完成修改后，向用户展示修改摘要并等待确认。

---

### 🛑 步骤 5：配置 DRAM（cache_ld.h）[依赖步骤1完成]

#### ⚠️ 执行前置条件（REQUIRED）
**确保已完成：**
- [x] 步骤1已通过用户确认（需要知道旧项目的 DRAM 配置）

#### ⚠️ 重要：DRAM 规则的三层优先级

**本步骤不以"旧项目 cache_ld.h"为准！** DRAM 规则有独立的三层逻辑：

| 规则层 | 内容 | 处理方式 |
|--------|------|---------|
| **第 1 层（硬规则）** | ALS/地磁/Pedometer/BARO/SAR | **必须注释**，无论旧项目是否启用 |
| **第 2 层（旧项目过滤）** | MSC/Elevator/Vehicle/Flicker | **仅旧项目已有的**才保留启用；旧项目没有的注释 |
| **第 3 层（新基线默认）** | Elevator | 新项目默认加电梯模式，保留启用 |

#### DRAM 规则表

| 放入 DRAM | 不放入 DRAM |
|-----------|-------------|
| MSC（若旧项目有） | ALS（光感）**→ 硬规则，必须注释** |
| Elevator **→ 新代码默认加** | Magnetometer（地磁）**→ 硬规则，必须注释** |
| Vehicle（若旧项目有） | Pedometer **→ 硬规则，必须注释** |
| Flicker（若旧项目有） | BARO **→ 硬规则，必须注释** |
| | SAR **→ 硬规则，必须注释** |

> ⚠️ 说明：表中"放入 DRAM"列中的 sensor，**首先检查旧项目是否有**。旧项目有才放 DRAM，旧项目没有就不要新增。Elevator 作为新项目默认 feature 始终保留。

#### 操作
1. 读取新项目的 cache_ld.h
2. 按三层规则逐段处理：
   - 不放入 DRAM 的段（ALS/地磁/Pedometer/BARO/SAR）：全部注释（`//#define CACHE_xxx`）
   - 放入 DRAM 的段（MSC/Elevator/Vehicle/Flicker）：检查旧项目 project.mk 是否有对应宏
     - 有 → 启用
     - 无 → 注释
   - Elevator：保留启用
   - 与 sensor 无关的段（VOW/SMARTPA/AUDIOFW/ULTRASOUND）：保留新基线配置，不动

#### ✅ 完成确认
完成修改后，向用户展示最终启用/注释的段列表并等待确认。

---

### 🛑 步骤 6：处理 msensor 文件 [依赖步骤1完成]

#### ⚠️ 执行前置条件（REQUIRED）
**确保已完成：**
- [x] 步骤1已确认旧项目路径

#### 操作
以旧项目为准，处理 msensor 目录：

1. **保留**：旧项目和新项目都有的子目录，保留不动
2. **删除**：新项目有但旧项目没有的子目录（如 vtc/），删除
3. **复制**：旧项目有但新项目没有的文件，从旧项目复制过来

**如果旧项目没有 msensor 目录或目录为空**：跳过此步骤，向用户说明无需处理。

**推荐删除方法（Windows 网络映射盘环境）：**
```powershell
# 先删文件
Remove-Item "文件路径" -Force
# 或使用 DeleteFile 工具逐文件删除
# 空目录可能删不掉（网络盘限制），但不影响编译
```

**常见 msensor 子目录：**
- `memsic/` - 地磁算法库（Memsic）
- `qst/` - 地磁算法库（QST）
- `vtc/` - 地磁算法库（VTC）
- 其他供应商地磁算法库

#### ✅ 完成确认
完成处理后，向用户展示文件变更列表并等待确认。

---

### 🛑 步骤 7：升级后验证 [依赖所有前置步骤完成]

#### ⚠️ 执行前置条件（REQUIRED）
**确保已完成：**
- [x] 步骤 3-6 全部完成

#### 操作
调用 **scp-sensor-check** Skill 对新项目进行全量 sensor 配置验证，确保：

- [ ] 所有 = yes 的 sensor 宏均通过构建级或源码级生效
- [ ] 不存在死宏（= yes 但无任何代码引用）
- [ ] DTS 配置与 project.mk 宏一致
- [ ] 库文件依赖完整
- [ ] 重点关注 P1 级别问题（功能缺失）并协助修复

#### ✅ 完成确认
输出验证报告，标记所有 P1/P2/P3 问题，等待用户确认是否需要修复。

---

## 常见问题

### dts.c 文件写入后为空

**现象**：使用 Write 工具写入 dts.c 后，文件内容为空。

**解决**：重新读取旧项目的源文件，然后完整写入。

### DRAM 配置理解错误

**误解1**：以为"以旧项目为准"意味着把旧项目的 cache_ld.h 全部照搬过来。

**正确理解**：DRAM 规则表有独立优先级。"不放入 DRAM"列是硬规则（必须注释），"放入 DRAM"列需要旧项目确有该 sensor 才启用。

**误解2**：认为地磁需要放入 DRAM 或注释掉光感配置。

**正确理解**：光感、地磁这些**不要放在 dram**。

### 文件复制失败（网络映射盘）

**现象**：使用 xcopy/cp/robocopy 复制文件时遇到权限错误或文件属性修改错误。

**错误信息**：`错误 50 (0x00000032) 正在更改文件属性` 或 `不支持该请求`

**解决**：
- 使用 PowerShell 的 `New-Item` 创建目录
- 使用 `Copy-Item` 逐个文件复制
- 避免使用通配符或批量复制命令
- 删除文件使用 `DeleteFile` 工具，空目录残留不影响编译

### OIS 配置误操作

**现象**：错误地将旧项目的 OIS 配置同步到新项目，或删除新项目原有的 OIS 配置。

**正确做法**：OIS 不由 sensor 负责，OIS 相关配置**不需要修改**，保持新项目原有配置即可。

### 驱动专属宏残留

**现象**：删除了芯片 support 宏（如 STK33562），但附属宏（如 CHANNEL_ALS、ALS_SWITCH_GAIN）仍然保留。

**正确做法**：project.mk 修改完成后，逐行扫描确认每个宏都有对应的芯片驱动已启用。不确定归属的宏直接询问用户。

### 宏名在不同基线变化

**现象**：新分支用 `CFG_ANTI_TOUCH_SUPPORT`，老分支用 `CFG_ANTI_TOUCH_ULTRASOUND_SUPPORT`。

**正确做法**：搜索 sensorhub.mk 和 C 源码，查看各自编译的 `.c` 文件和链接的 `.a` 库。若为不同实现方案，以旧项目为准选择对应宏名。

---

## 🎯 快速检查清单（模型自查用）

在每个步骤执行前，模型必须自问：
- [ ] 我是否已经向用户询问了所有必要信息？
- [ ] 我是否在等待用户确认后才继续？
- [ ] 我是否使用了旧项目的实际数据而非文档示例？
- [ ] 我是否避免了自行假设任何配置？
- [ ] 我是否明确告知用户当前进度和下一步计划？
- [ ] 我是否正确处理了抬手亮屏配置（CFG_WAKEUP_SUPPORT = no, CFG_TRANS_WAKEUP_SUPPORT = yes）？
- [ ] 我是否正确处理了 OIS 配置（保持新项目原有配置，不需要修改）？
- [ ] 我是否检查了 CFG_SIGNIFICANT_MOTION_SUPPORT = yes？
- [ ] 我是否正确应用了 DRAM 三层规则（不放入列硬注释；放入列查旧项目）？
- [ ] 我是否检查了驱动专属宏的联动删除（无残留附属宏）？
- [ ] 我是否在升级完成后调用了 scp-sensor-check 验证？

**如果以上任何一题答案为"否"，立即停止并修正！**
