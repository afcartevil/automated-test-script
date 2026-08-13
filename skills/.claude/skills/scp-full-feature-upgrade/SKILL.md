---
name: "scp-full-feature-upgrade"
description: "MTK Sensorhub 3.0 SCP 8大核心特性升级子模块。处理自研抬手亮屏/口袋模式/电梯模式/乘车检测/摇一摇/翻转检测/正背面物理距感防误触 8 个特性的迁移 + 验证。以旧项目代码为准，模型自主从代码中提取配置，用户无需提供任何信息。默认策略：新基线独有特性全部不添加。⚠️ MANDATORY: 必须先调用 scp-upgrade 完成 project.mk/dts.c/DRAM 基础迁移，再处理这 8 个特性的差异。"
---

# MTK Sensorhub 3.0 SCP 全功能特性升级

## 0. 与 scp-upgrade 的关系

- 本 Skill 是 [scp-upgrade](file:///d:\Users\zijun.du\.trae-cn\skills\scp_upgrade\SKILL.md) 的子模块，**不替代**基础升级流程
- **调用顺序**：先 scp-upgrade 完成 project.mk/dts.c/cache_ld.h/msensor/alslib 基础迁移
- 再调用本 Skill 专门处理 8 大特性的差异
- **本 Skill 假定 scp-upgrade 已提供旧/新项目路径，本 Skill 不再询问用户**

## ⛔ 强制执行规则（MUST READ FIRST）

**🚨 违反任何一条都将导致任务失败：**

### 规则 1：以旧项目代码为准
- ❌ **FORBIDDEN**：自行假设 8 大特性的启用状态、参数值、依赖关系
- ❌ **FORBIDDEN**：使用模板默认值、推断值、文档示例值
- ✅ **REQUIRED**：所有判断必须基于**实际读取**的旧/新项目代码
- ✅ **REQUIRED**：8 大特性是否启用 → 以旧项目 project.mk 实际值为准
- ✅ **REQUIRED**：新基线独有的特性 → 默认不添加（与旧项目保持一致）

### 规则 2：用户无需提供信息
本 Skill **不向用户询问**以下内容（模型自主从代码中获取）：
- 8 个特性的宏值
- dts.c 段参数
- sensorhub.mk 联动状态
- 库文件存在性
- DRAM 配置

**唯一需要用户决策的**：新基线独有的特性（步骤 2 中识别）是否添加

### 规则 3：路径必须先定位后操作
- ❌ **FORBIDDEN**：假设 cache_ld.h 的位置（部分项目在 `{项目}/inc/`，部分在 `{平台}/inc/`）
- ✅ **REQUIRED**：操作前必须用 `Glob` 工具定位所有目标文件

### 规则 4：链接库文件必须存在
- sensorhub.mk 中引用的 `-lxxx` 库必须在 `middleware/sensorhub/algos/?*/xxx/` 下实际存在
- 引用的 `VIRTUAL_DRV_DIR/xxx/xxx.c` 必须在 `middleware/sensorhub/drivers/virtual/xxx/` 下实际存在
- 缺失时**必须**在 P1 问题中报告

### 规则 5：联动宏必须同步处理
- `CFG_TRANS_WAKEUP_SUPPORT` ↔ `CFG_WAKEUP_SUPPORT`（必须同时改）
- `CFG_ELEVATOR_DETECT_SUPPORT` ↔ `CFG_ELEVATOR_DETECT_NEW_SUPPORT`（询问用户）
- `CFG_ANTI_TOUCH_SUPPORT` ≠ `CFG_ANTI_TOUCH_ULTRASOUND_SUPPORT`（两个不同特性，不混淆）

---

## 8 大特性卡片（模型自主从代码中读取状态）

### 特性 1：自研抬手亮屏 (CFG_TRANS_WAKEUP_SUPPORT)

| 项目 | 详情 |
|------|------|
| 宏 | `CFG_TRANS_WAKEUP_SUPPORT`（业务规则统一 yes） |
| 联动 | `CFG_WAKEUP_SUPPORT = no`（必须同时设置） |
| sensorhub.mk | `$(VIRTUAL_DRV_DIR)/pickup/pickup.c` + `-lpickup` |
| dts.c 段 | 必有，含 `name=pickup` + `params1-6` |
| 模型自主处理 | 1. 读取旧项目 dts.c 中 `#ifdef CFG_TRANS_WAKEUP_SUPPORT` 段<br>2. 完整复制到新项目（逐字段 params）<br>3. 写入后向用户报告 |
| 验证 | 宏正确 + dts.c 段参数正确 + `-lpickup` 库存在 + `pickup.c` 存在 |

**参考位置（od_a16）**：
- project.mk：[x6896_p586a:97](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/project.mk#L97)
- sensorhub.mk：[mt6858:430](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/platform/features/sensorhub.mk#L430)
- dts.c：[x6896_p586a:223](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/sensor/dts.c#L223)

### 特性 2：口袋模式 (CFG_HEAD_POSTURE_SUPPORT)

| 项目 | 详情 |
|------|------|
| 宏 | `CFG_HEAD_POSTURE_SUPPORT`（以旧项目为准） |
| sensorhub.mk | `$(VIRTUAL_DRV_DIR)/head_posture/head_posture.c` + `-lhead_posture` |
| dts.c 段 | 无 |
| 模型自主处理 | 1. 读取旧项目 project.mk 中该宏值<br>2. 写入新项目（与旧项目一致） |
| 验证 | 宏正确 + `-lhead_posture` 库存在 + `head_posture.c` 存在 |

**参考位置（od_a16）**：
- project.mk：[x6896_p586a:101](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/project.mk#L101)
- sensorhub.mk：[mt6858:525](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/platform/features/sensorhub.mk#L525)

### 特性 3：电梯模式 (CFG_ELEVATOR_DETECT_SUPPORT)

| 项目 | 详情 |
|------|------|
| 宏 | `CFG_ELEVATOR_DETECT_SUPPORT`（以旧项目为准） |
| 联动宏 | `CFG_ELEVATOR_DETECT_NEW_SUPPORT`（新实现，可选，**询问用户**） |
| sensorhub.mk | `$(VIRTUAL_DRV_DIR)/elevator_detect/elevator_detect.c` + `-lelevator_detect` 或 `-lelevator_detect_new` |
| dts.c 段 | 无 |
| 模型自主处理 | 1. 读取旧项目 project.mk 中两个宏的值<br>2. 询问用户 ELEVATOR_DETECT_NEW_SUPPORT 是否启用<br>3. 写入新项目 |
| DRAM | `CACHE_ELEVATOR_TEXT/DATA` 段（按旧项目决定启用/注释） |
| 验证 | 宏与旧项目一致 + DRAM 段配置正确 + 算法库存在（二选一） |

**参考位置（od_a16）**：
- project.mk：[x6896_p586a:105](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/project.mk#L105)
- sensorhub.mk：[mt6858:454-461](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/platform/features/sensorhub.mk#L454)
- cache_ld.h：[x6896_p586a:62](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/inc/cache_ld.h#L62)

### 特性 4：乘车检测 (CFG_VEHICLE_SUPPORT)

| 项目 | 详情 |
|------|------|
| 宏 | `CFG_VEHICLE_SUPPORT`（以旧项目为准） |
| sensorhub.mk | `$(VIRTUAL_DRV_DIR)/vehicle/vehicle.c` + `-lvehicle` |
| dts.c 段 | 必有，含 `name=vehicle` + `params0-5` |
| 模型自主处理 | 1. 读取旧项目宏值<br>2. 读取旧项目 dts.c 段（逐字段）<br>3. 写入新项目 |
| DRAM | `CACHE_VEHICLE_TEXT/DATA` 段（按旧项目决定） |
| 验证 | 宏 + dts.c 段 + sensorhub.mk ifeq 块 + 库 + DRAM 段 |

**参考位置（od_a16）**：
- project.mk：[x6896_p586a:104](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/project.mk#L104)
- sensorhub.mk：[mt6858:464](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/platform/features/sensorhub.mk#L464)
- dts.c：[x6896_p586a:234](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/sensor/dts.c#L234)
- cache_ld.h：[x6896_p586a:80](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/inc/cache_ld.h#L80)

### 特性 5：摇一摇 (CFG_SHAKE_DETECT_SUPPORT)

| 项目 | 详情 |
|------|------|
| 宏 | `CFG_SHAKE_DETECT_SUPPORT`（以旧项目为准） |
| sensorhub.mk | `$(VIRTUAL_DRV_DIR)/shake_detect/shake_detect.c` + `-lshake_detect` |
| dts.c 段 | 必有，含 `name=shake_detect` + `params1-6` |
| 模型自主处理 | 1. 读取旧项目宏值<br>2. 读取旧项目 dts.c 段（逐字段）<br>3. 写入新项目 |
| 验证 | 宏 + dts.c 段 + 库 + 源文件 |

**参考位置（od_a16）**：
- project.mk：[x6896_p586a:102](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/project.mk#L102)
- sensorhub.mk：[mt6858:436](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/platform/features/sensorhub.mk#L436)
- dts.c：[x6896_p586a:244](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/sensor/dts.c#L244)

### 特性 6：翻转检测 (CFG_FLIP_DETECT_SUPPORT)

| 项目 | 详情 |
|------|------|
| 宏 | `CFG_FLIP_DETECT_SUPPORT`（以旧项目为准） |
| sensorhub.mk | `$(VIRTUAL_DRV_DIR)/flip_detect/flip_detect.c` + `-lflip_detect` |
| dts.c 段 | 必有，含 `name=flip_detect` + `params0-8` |
| 模型自主处理 | 1. 读取旧项目宏值<br>2. 读取旧项目 dts.c 段（逐字段）<br>3. 写入新项目 |
| 验证 | 宏 + dts.c 段 + 库 + 源文件 |

**参考位置（od_a16）**：
- project.mk：[x6896_p586a:103](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/project.mk#L103)
- sensorhub.mk：[mt6858:442](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/platform/features/sensorhub.mk#L442)
- dts.c：[x6896_p586a:254](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/sensor/dts.c#L254)

### 特性 7：正面物理距感防误触 (CFG_ANTI_TOUCH_SUPPORT) ⚠️区分两个宏

| 项目 | 详情 |
|------|------|
| 宏 | `CFG_ANTI_TOUCH_SUPPORT`（以旧项目为准） |
| ⚠️ 注意 | 还有一个 `CFG_ANTI_TOUCH_ULTRASOUND_SUPPORT` 是**不同特性**（超声防误触） |
| sensorhub.mk | `$(VIRTUAL_DRV_DIR)/anti_touch/anti_touch.c` + `-lanti_touch` |
| dts.c 段 | 无 |
| 依赖 | 依赖 PS（距离传感器）输入，PS 未启用则功能失效 |
| 模型自主处理 | 1. 读取旧项目宏值（**注意是 ANTI_TOUCH 而非 ANTI_TOUCH_ULTRASOUND**）<br>2. 确认 PS 物理 sensor 已配置（自动从 project.mk 验证）<br>3. 写入新项目 |
| 验证 | 宏 + 与 ANTI_TOUCH_ULTRASOUND 区分 + 库 + PS 已配置 |

**参考位置（od_a16）**：
- project.mk：[x6896_p586a:100](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/project.mk#L100)
- ANTI_TOUCH_ULTRASOUND（不要混淆）：[x6896_p586a:99](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/x6896_p586a/project.mk#L99)
- sensorhub.mk（ANTI_TOUCH）：[mt6858:513](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/platform/features/sensorhub.mk#L513)
- sensorhub.mk（ANTI_TOUCH_ULTRASOUND）：[mt6858:448](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6858/platform/features/sensorhub.mk#L448)

### 特性 8：背部物理距感防误触 (CFG_POCKET_DETECT_BACK_SUPPORT)

| 项目 | 详情 |
|------|------|
| 宏 | `CFG_POCKET_DETECT_BACK_SUPPORT`（以旧项目为准） |
| sensorhub.mk | 需在 `platform/features/sensorhub.mk` 中搜索 ifeq 块（mt6789:595 有，mt6858 待确认） |
| dts.c 段 | 无 |
| 模型自主处理 | 1. 读取旧项目宏值<br>2. 写入新项目 |
| 验证 | 宏 + sensorhub.mk ifeq 块 + 库文件存在 |

**参考位置（od_a16）**：
- project.mk：[x6858_h8917:83](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6789/x6858_h8917/project.mk#L83)
- sensorhub.mk：[mt6789:595](file:///z:/code/od_A16/vendor/mediatek/proprietary/tinysys/scp/project/RV55_A/mt6789/platform/features/sensorhub.mk#L595)

---

## 升级流程

### 步骤 1：前置依赖与路径定位 [模型自主执行]

#### 前置条件
- [x] scp-upgrade 步骤 1-7 已完成（旧/新项目路径已传入）
- [x] scp-upgrade 已提供 SCP_DIR

#### 模型自主操作
1. **用 Glob 定位**所有目标文件
2. **输出路径定位表**（向用户展示确认）

**示例路径定位表**：

| 文件 | 实际路径 |
|------|---------|
| project.mk | `project/RV55_A/mt6858/x6896_p586a/project.mk` |
| dts.c | `project/RV55_A/mt6858/x6896_p586a/sensor/dts.c` |
| cache_ld.h | `project/RV55_A/mt6858/x6896_p586a/inc/cache_ld.h`（**位置不固定**） |
| sensorhub.mk | `project/RV55_A/mt6858/platform/features/sensorhub.mk` |

### 步骤 2：识别新基线独有特性 [模型自主，默认不添加]

#### 模型自主操作
对比旧/新 project.mk，识别"新基线有但旧项目无"的 CFG_ 宏（8 大特性相关）。

**默认策略：全部不添加（与旧项目保持一致）**。
在终验表格中标注"已采用默认策略，新基线独有特性未添加"。

列出差异供参考，但**不询问用户**，直接跳过差异项。

### 步骤 3：逐特性迁移 project.mk [模型自主执行，自动写入]

#### 模型自主操作
按顺序处理 8 个特性：
1. 读取旧项目 project.mk 中该宏值
2. 写入新项目
3. 检查联动宏
4. 展示修改计划后**立即自动写入**

#### 输出
```markdown
📋 8 大特性宏迁移表（模型自动生成）：
| # | 宏 | 旧值 | 新值 | 说明 |
|---|-----|:--:|:--:|------|
| 1 | CFG_TRANS_WAKEUP_SUPPORT | yes | yes | 业务规则 |
| 2 | CFG_WAKEUP_SUPPORT | no | no | 联动 |
| 3 | CFG_HEAD_POSTURE_SUPPORT | yes | yes | 以旧为准 |
| 4 | CFG_ELEVATOR_DETECT_SUPPORT | yes | yes | 以旧为准 |
| 5 | CFG_ELEVATOR_DETECT_NEW_SUPPORT | yes | yes | 步骤2决定 |
| 6 | CFG_VEHICLE_SUPPORT | yes | yes | 以旧为准 |
| 7 | CFG_SHAKE_DETECT_SUPPORT | yes | yes | 以旧为准 |
| 8 | CFG_FLIP_DETECT_SUPPORT | yes | yes | 以旧为准 |
| 9 | CFG_ANTI_TOUCH_SUPPORT | yes | yes | ≠ ULTRASOUND |
| 10 | CFG_POCKET_DETECT_BACK_SUPPORT | no | no | 以旧为准 |
```

#### ✅ 自动写入
**展示后立即自动写入，无需用户确认。**

### 步骤 4：补 dts.c 段 [模型自主执行]

#### 触发条件
旧项目 `#ifdef` 块存在，新项目缺失时触发。

#### 模型自主操作
对 4 个需要 dts.c 段的特性（自研抬手亮屏/乘车/摇一摇/翻转检测）：
1. 读取旧项目 dts.c 段（**逐字段复制**）
2. 写入新项目
3. 写入前展示 params 对比表

### 步骤 5：sensorhub.mk 联动验证 [模型自主执行]

#### 模型自主操作
对每个特性：
1. 在新项目 `platform/features/sensorhub.mk` 中搜索 `ifeq ($([宏名]_SUPPORT),yes)`
2. 用 Glob 在 `middleware/sensorhub/` 下确认 `.c` 和 `.a` 存在
3. 缺失标记为 P1 问题

#### 输出
```markdown
📋 sensorhub.mk 联动 + 库存在性检查（模型自动）：
| # | 宏 | ifeq | .c | .a | 状态 |
|---|-----|:----:|:--:|:--:|:----:|
| 1 | CFG_TRANS_WAKEUP_SUPPORT | ✅ | ✅ | ✅ | OK |
| 2 | CFG_HEAD_POSTURE_SUPPORT | ❌ | ✅ | ✅ | P1 |
| ... |
```

### 步骤 6：DRAM 配置 [模型自主执行]

#### DRAM 规则（模型自主应用）

| 规则层 | 内容 | 处理方式 |
|--------|------|---------|
| **第 1 层（硬规则）** | ALS/地磁/Pedometer/BARO/SAR | **必须注释** |
| **第 2 层（旧项目过滤）** | MSC/Elevator/Vehicle/Flicker | 仅旧项目已启用才保留 |

#### 模型自主操作
1. 定位 cache_ld.h
2. 按规则逐段处理

### 步骤 7：调用 scp-sensor-check 验证 [模型自主执行]

**调用**：
```
调用 scp-sensor-check Skill 对新项目做全量验证，重点关注这 8 个特性
```

#### 验证维度（模型自主检查）
- [ ] 8 个宏的最终值正确
- [ ] dts.c 中 `#ifdef` 段参数正确
- [ ] sensorhub.mk 中 ifeq 块存在
- [ ] 引用的 `.c` 源文件存在
- [ ] 引用的 `.a` 算法库存在
- [ ] cache_ld.h 中 DRAM 配置正确
- [ ] 无死宏
- [ ] 联动宏正确
- [ ] ANTI_TOUCH 与 ANTI_TOUCH_ULTRASOUND 区分正确

### 步骤 8：编译验证 [人工]

**操作**：
1. 用户在新项目中执行编译命令
2. 若编译失败，模型协助定位错误源

**注意**：本 Skill **不能执行编译**，必须由用户完成

---

## 常见问题

### Q1：cache_ld.h 位置不确定

**解决**：用 `Glob` 搜索 `{项目}/**/cache_ld.h` 定位

### Q2：sensorhub.mk 中无 ifeq 块

**解决**：模型从其他平台复制 ifeq 块到本平台 sensorhub.mk 中

### Q3：算法库文件不存在

**解决**：模型从旧基线或其他平台复制 `algos/?*/{feature}/*.a` 到新基线

### Q4：误把 ANTI_TOUCH_SUPPORT 和 ANTI_TOUCH_ULTRASOUND_SUPPORT 混淆

**解决**：搜索 sensorhub.mk ifeq 块确认实际使用的是哪个宏

### Q5：电梯模式新旧实现选择

**解决**：在步骤2询问用户，若旧项目有 ELEVATOR_DETECT_NEW_SUPPORT = yes 则新项目也用 yes

### Q6：dts.c 段顺序错误

**解决**：dts.c 中各段必须按 sensorhub.mk 中 ifeq 块的顺序排列

### Q7：cache_ld.h 路径通配符不匹配

**解决**：检查 `CACHE_xxx` 段中的路径通配符 `?*` 是否与实际路径匹配

---

## 🎯 快速检查清单（模型自查用）

- [ ] 我是否已经从 scp-upgrade 获得了旧/新项目路径？
- [ ] 我是否使用了 Glob/Read 工具**实际读取**了 8 大特性相关文件？
- [ ] 我是否避免了自行假设任何配置（宏值、参数、feature 启用）？
- [ ] 我是否避免了向用户询问可从代码中获取的细节？
- [ ] 我是否正确定位了 cache_ld.h / sensorhub.mk / dts.c 的实际路径？
- [ ] 我是否补全了联动宏（CFG_WAKEUP_SUPPORT / CFG_ELEVATOR_DETECT_NEW_SUPPORT）？
- [ ] 我是否区分了 ANTI_TOUCH 与 ANTI_TOUCH_ULTRASOUND？
- [ ] 我是否在 dts.c 中逐字段复制了 params？
- [ ] 我是否检查了所有 sensorhub.mk 引用的库文件实际存在？
- [ ] 我是否在升级完成后调用了 scp-sensor-check 验证？

**如果以上任何一题答案为"否"，立即停止并修正！**

---

## 🛑 强制终验表格（不可跳过）

**此表格必须在所有步骤完成后逐行填写，不可省略。**

### project.mk 终验

| # | 宏 | 旧值 | 新值 | 迁移? | 说明 |
|---|-----|:--:|:--:|:--:|------|
| 1 | CFG_TRANS_WAKEUP_SUPPORT | yes | yes | ✅/❌ | 业务规则 |
| 2 | CFG_WAKEUP_SUPPORT | no | no | ✅/❌ | 联动 |
| 3 | CFG_HEAD_POSTURE_SUPPORT | | | ✅/❌ | |
| 4 | CFG_ELEVATOR_DETECT_SUPPORT | | | ✅/❌ | 按旧项目 |
| 5 | CFG_ELEVATOR_DETECT_NEW_SUPPORT | | | ✅/❌ | 默认与旧项目一致 |
| 6 | CFG_VEHICLE_SUPPORT | | | ✅/❌ | |
| 7 | CFG_SHAKE_DETECT_SUPPORT | | | ✅/❌ | |
| 8 | CFG_FLIP_DETECT_SUPPORT | | | ✅/❌ | |
| 9 | CFG_ANTI_TOUCH_SUPPORT | | | ✅/❌ | ≠ ULTRASOUND |
| 10 | CFG_POCKET_DETECT_BACK_SUPPORT | | | ✅/❌ | |

### dts.c 段终验

| # | #ifdef 宏 | 旧项目存在? | 新项目存在? | 参数一致? |
|---|-----------|:--:|:--:|:--:|
| 1 | CFG_TRANS_WAKEUP_SUPPORT | | | ✅/❌ |
| 2 | CFG_VEHICLE_SUPPORT | | | ✅/❌ |
| 3 | CFG_SHAKE_DETECT_SUPPORT | | | ✅/❌ |
| 4 | CFG_FLIP_DETECT_SUPPORT | | | ✅/❌ |

### sensorhub.mk 联动终验

| # | 宏 | ifeq 块存在? | .c 源存在? | .a 库存在? |
|---|-----|:--:|:--:|:--:|
| 1 | CFG_TRANS_WAKEUP_SUPPORT | ✅/❌ | ✅/❌ | ✅/❌ |
| 2 | CFG_HEAD_POSTURE_SUPPORT | ✅/❌ | ✅/❌ | ✅/❌ |
| 3 | CFG_ELEVATOR_DETECT_SUPPORT | ✅/❌ | ✅/❌ | ✅/❌ |
| 4 | CFG_ELEVATOR_DETECT_NEW_SUPPORT | ✅/❌ | N/A | ✅/❌ |
| 5 | CFG_VEHICLE_SUPPORT | ✅/❌ | ✅/❌ | ✅/❌ |
| 6 | CFG_SHAKE_DETECT_SUPPORT | ✅/❌ | ✅/❌ | ✅/❌ |
| 7 | CFG_FLIP_DETECT_SUPPORT | ✅/❌ | ✅/❌ | ✅/❌ |
| 8 | CFG_ANTI_TOUCH_SUPPORT | ✅/❌ | ✅/❌ | ✅/❌ |
| 9 | CFG_POCKET_DETECT_BACK_SUPPORT | ✅/❌ | ✅/❌ | ✅/❌ |

### DRAM 终验

| # | 段 | 规则 | 配置? |
|---|-----|------|:--:|
| 1 | CACHE_ELEVATOR_TEXT | 按旧项目 | ✅/❌ |
| 2 | CACHE_ELEVATOR_DATA | 按旧项目 | ✅/❌ |
| 3 | CACHE_VEHICLE_TEXT | 按旧项目 | ✅/❌ |
| 4 | CACHE_VEHICLE_DATA | 按旧项目 | ✅/❌ |

**终验规则**：
- 最后一列全部 ✅ 才算通过
- 如有 ❌，必须先修复才能宣告完成
- 不要总结为"已验证通过"，必须展示完整表格
