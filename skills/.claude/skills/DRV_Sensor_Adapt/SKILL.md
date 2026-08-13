---
name: "mtk-sensorhub-3.0-upgrade"
description: "MTK Sensorhub 3.0 全量升级总控 Skill。用户升级 sensor 配置时先调用此 Skill，由它自动推导所有子模块路径，按依赖顺序调度 scp-upgrade / scp-full-feature-upgrade / mtk-sensor-dts-config / tranprojects-upgrade / scp-sensor-check / lid-check 完成全量升级和验证。以旧项目代码为准，用户只需提供旧/新项目根目录，模型自主推导所有子模块路径和配置。Invoke when user needs to perform a full MTK Sensorhub 3.0 upgrade across SCP / kernel DTS / vendor/transsion/projects / NVRAM LID."
---

# MTK Sensorhub 3.0 全量升级总控

## ⛔ 强制执行规则（MUST READ FIRST）

**🚨 这些规则优先级最高，违反任何一条都将导致任务失败：**

### 规则 1：用户只需提供 2 项必要信息
用户**必须**提供的信息（仅 2 项）：
- **旧项目根目录路径**（如 `z:\code\od_A14`，标准 AOSP 项目根目录）
- **新项目根目录路径**（如 `z:\code\od_A16`，标准 AOSP 项目根目录）

以下信息模型**自主推导**，**绝不询问用户**：
- SCP 项目路径（`vendor/mediatek/proprietary/tinysys/scp/project/{PROCESSOR}/{PLATFORM}/{PROJECT}/`）
- kernel_device_modules 路径（`kernel/kernel_device_modules-*/`）
- vendor/transsion/projects 路径（`vendor/transsion/projects/{PROJECT}/`）
- cgen 路径（`vendor/mediatek/proprietary/custom/{PROJECT}/cgen/`）
- 项目代号（从目录名推断）
- PROCESSOR / PLATFORM / PROJECT（从 SCP 目录结构推断）

🛑 **如果用户未提供 2 项必要信息中的任何一项，立即停止并询问。**

### 规则 2：以旧项目代码为准
- ❌ **FORBIDDEN**：自行假设 sensor 列表、feature 启用状态、参数值、路径结构
- ❌ **FORBIDDEN**：套用文档示例值、固定模板值、推断值
- ✅ **REQUIRED**：所有配置必须从**旧项目源文件**中**实际读取**后判断
- ✅ **REQUIRED**：旧项目配置与文档/模板不一致时，**以旧项目为准**

### 规则 3：按依赖顺序自动调度，不跳过、不并行、不询问
- 各子 Skill **必须按阶段顺序串行执行**，前一阶段完成后**立即**进入下一阶段
- **绝不允许**在阶段间停下来询问用户"是否继续"、"确认"或"下一步"
- 不允许并行调用多个升级 Skill（避免文件冲突）
- 某阶段路径推导失败 → 标记为 "Skipped" 并报告原因，继续下一阶段

### 规则 4：各阶段自动串行，仅在阻塞时暂停
- 各子 Skill **按阶段顺序自动串行执行**，前一阶段完成后自动进入下一阶段
- 每阶段完成后展示终验摘要，但**不等待用户确认**，直接继续
- 阶段间不响应"跳过"或"回退"指令；如有需要，在总控终验完成后统一处理
- 某阶段路径推导失败 → 标记为 "Skipped" 并报告原因，继续下一阶段
- **仅在以下阻塞情况暂停**：
  - 关键文件完全不存在且无法自动定位
  - 出现多个候选方案（多个 PROJECT / PLATFORM 等）
  - P1 级别问题需要用户决定修复方案

### 规则 5：scp-full-feature-upgrade 阶段 3 的"新基线独有特性"决策
- **总控自动采用方案 A**：**全部不添加（与旧项目保持一致）**
- 此决策在阶段 3 终验摘要中明确标注"已采用方案 A，新基线独有特性未添加"
- **总控升级完成后**：模型列出"新基线独有但未添加的特性"清单，用户可**选择性地**单独调用 `scp-full-feature-upgrade` Skill 处理想启用的特性
- 这样保证"全量自动 + 最小用户输入"原则不被破坏

---

## 概述

本 Skill 是 MTK Sensorhub 3.0 升级的**唯一入口**。用户只需提供旧/新项目根目录，本 Skill 自动完成以下全部工作：

1. **路径推导**：从根目录自动推导 SCP / kernel / vendor/transsion / cgen 等各子模块路径
2. **阶段调度**：按依赖顺序自动调用 6 个子 Skill
3. **结果汇总**：每个阶段终验后汇总为总控终验报告

### 与子 Skill 的关系

```
mtk-sensorhub-3.0-upgrade（本 Skill — 总控入口）
  │
  ├─ 阶段 1: 路径推导 [模型自主]
  │
  ├─ 阶段 2: SCP 基础升级 [调用 scp-upgrade]
  │     └─ project.mk / dts.c / cache_ld.h / msensor / alslib
  │
  ├─ 阶段 3: SCP 8大特性升级 [调用 scp-full-feature-upgrade]
  │     └─ 依赖阶段 2；抬手亮屏/口袋/电梯/乘车/摇一摇/翻转/正背面防误触
  │
  ├─ 阶段 4: Kernel DTS 升级 [调用 mtk-sensor-dts-config]
  │     └─ tran_custom.config → 新 DTS
  │
  ├─ 阶段 5: vendor/transsion/projects 升级 [调用 tranprojects-upgrade]
  │     └─ device-vext.mk / ProjectConfig.mk / sensor_config.json
  │
  ├─ 阶段 6: 全量验证 [调用 scp-sensor-check]
  │     └─ 新项目 SCP sensor 配置生效验证
  │
  ├─ 阶段 7: LID 检查 [调用 lid-check]
  │     └─ NVRAM LID 枚举/数组一致性（路径存在则执行，不存在则 Skipped）
  │
  └─ 阶段 8: 总控终验 [模型自主]
        └─ 汇总所有阶段终验结果
```

---

## 路径推导规则

用户提供**项目根目录**后，模型用 `Glob` 工具按以下规则推导各子模块路径。

### 推导逻辑

```
旧项目根目录 = {OLD_ROOT}
新项目根目录 = {NEW_ROOT}

1. SCP_DIR
   {OLD_ROOT}/vendor/mediatek/proprietary/tinysys/scp/
   {NEW_ROOT}/vendor/mediatek/proprietary/tinysys/scp/
   → 若不存在，标记 "SCP: 路径不存在，Skipped"

2. SCP 项目路径（逐层推导）
   {SCP_DIR}/project/           → Glob 找 PROCESSOR（RV55_A / RV33_A）
   {SCP_DIR}/project/{PROCESSOR}/  → Glob 找 PLATFORM（mt\d+）
   {SCP_DIR}/project/{PROCESSOR}/{PLATFORM}/  → Glob 找 PROJECT（项目目录）
   → 若任一层找不到唯一目录，列出候选供用户选择

3. kernel_device_modules
   新项目（标准 AOSP 根目录）:
     {NEW_ROOT}/kernel/kernel_device_modules-*/
   旧项目（兼容两种结构）:
     ├─ 方案 A: {OLD_ROOT}/kernel/kernel_device_modules-*/  (标准 AOSP 根目录，如 od_A14)
     └─ 方案 B: Glob 在 {OLD_ROOT}/tran_projects/ 下递归搜索
                kernel/kernel_device_modules-* 或 kernel-* 目录，
                取其父目录为 OLD_KERNEL_BASE_DIR
                例: {OLD_ROOT}/tran_projects/x6857/x6857_h782_a1_x6857b/x6857/
                    → 其下存在 kernel/kernel_device_modules-6.1/
                例: {OLD_ROOT}/tran_projects/x6850b/x6850b_h895_aa1/x6850b/
                    → 其下存在 kernel-5.10/
   → 方案 A 优先；不存在则尝试方案 B；都不存在则标记 "DTS: kernel 路径不存在，Skipped"

   最终导出变量：
   ├─ OLD_KERNEL_BASE_DIR = 方案A: {OLD_ROOT}  /  方案B: 搜索到的父目录
   └─ NEW_KERNEL_DIR      = {NEW_ROOT}/kernel/kernel_device_modules-*/

4. vendor/transsion/projects
   新项目（新基线，A14+）:
     {NEW_ROOT}/vendor/transsion/projects/{PROJECT}/
   旧项目（兼容三种结构）:
     ├─ 方案 A: {OLD_ROOT}/vendor/transsion/projects/{PROJECT}/  (A14+ 旧项目)
     ├─ 方案 B: {OLD_ROOT}/device/transsion/{PROJECT}/            (老 baseline，device 直接在根目录)
     └─ 方案 C: {OLD_ROOT}/tran_projects/{PROJECT}/.../device/transsion/{PROJECT}/  (部分 A12/A13 baseline)
     
     同时还需要搜索旧 ProjectConfig 文件，按以下优先级：
     ① {OLD_ROOT}/device/transsion/{PROJECT}/ProjectConfig.mk 或 ProjectConfig_overlay.mk
     ② {OLD_ROOT}/tran_projects/{PROJECT}/.../device/transsion/{PROJECT}/ProjectConfig_overlay.mk
   → 方案 A 优先；不存在则方案 B；都不存在方案 C；全部不存在则标记 "tranprojects: 路径不存在，Skipped"

5. cgen
   {OLD_ROOT}/vendor/mediatek/proprietary/custom/{PROJECT}/cgen/
   {NEW_ROOT}/vendor/mediatek/proprietary/custom/{PROJECT}/cgen/
   → 若不存在，标记 "LID: cgen 路径不存在，Skipped"
```

### 路径定位表（输出后自动继续）

推导完成后，必须展示以下表格：

```markdown
📋 路径定位（模型自动推导）：
├─ 用户输入旧根目录: {OLD_ROOT}
├─ 用户输入新根目录: {NEW_ROOT}
│
├─ 【SCP】
│   ├─ 旧 SCP_DIR:    ✅ {OLD_SCP_DIR}
│   ├─ 新 SCP_DIR:    ✅ {NEW_SCP_DIR}
│   ├─ PROCESSOR:     {PROCESSOR}
│   ├─ PLATFORM:      {PLATFORM}
│   ├─ PROJECT:       {PROJECT}
│   └─ 旧项目路径:     {OLD_PROJECT_DIR}
│
├─ 【Kernel DTS】
│   ├─ 旧 kernel base: ✅/⚠️ {OLD_KERNEL_BASE_DIR}  (方案A: AOSP根 / 方案B: tran_projects子路径)
│   └─ 新 kernel dir:  ✅/⚠️ {NEW_KERNEL_DIR}
│
├─ 【vendor/transsion/projects】
│   ├─ 旧路径:        ✅/⚠️ {OLD_TRANPROJECTS_DIR}  (方案A vendor/transsion/projects 或 方案B tran_projects)
│   └─ 新路径:        ✅/⚠️ {NEW_TRANPROJECTS_DIR}
│
└─ 【cgen】
    ├─ 旧 cgen:       ✅/⚠️ {OLD_CGEN_DIR}
    └─ 新 cgen:       ✅/⚠️ {NEW_CGEN_DIR}
```

🛑 **路径定位表展示后自动进入阶段 2，无需用户确认。**

---

## 阶段详情

### 阶段 1：路径推导 [模型自主执行]

**触发条件**：用户已提供旧/新项目根目录
**操作**：按"路径推导规则"自动推导所有子模块路径
**输出**：路径定位表（展示后自动继续）
**终验**（完成后自动进入阶段 2）：
- [ ] 旧/新项目根目录已提供
- [ ] SCP_DIR 已定位（新旧均存在）
- [ ] PROCESSOR / PLATFORM / PROJECT 已推导
- [ ] 路径定位表已展示
- [ ] **⚠️ 立即自动进入阶段 2，不等待用户回复**

---

### 阶段 2：SCP 基础升级 [调用 scp-upgrade]

**触发条件**：阶段 1 路径定位表已展示，且新旧 SCP_DIR 均存在。模型自动开始执行，不等待用户输入。
**调用方式**：
```
调用 scp-upgrade Skill，传入参数：
- 旧项目完整路径 = {OLD_PROJECT_DIR}
- 新基线完整路径 = {NEW_PROJECT_DIR}
- 项目名称/代号 = {PROJECT}
```
**执行内容**：scp-upgrade 的 7 个步骤（project.mk → dts.c → cache_ld.h → msensor → alslib → 验证）
**输出**：scp-upgrade 的终验表格（project.mk 终验 / 删除确认 / dts.c 终验 / alslib 终验）
**用户交互**：展示终验表格，自动进入下一阶段

**终验**（完成后自动进入阶段 3）：
- [ ] scp-upgrade 7 个步骤全部完成
- [ ] project.mk 终验表格最后一列全部 ✅
- [ ] dts.c 终验表格最后一列全部 ✅
- [ ] alslib 终验表格最后一列全部 ✅

---

### 阶段 3：SCP 8大特性升级 [调用 scp-full-feature-upgrade]

**触发条件**：阶段 2 完成后自动进入，无需用户确认
**依赖**：阶段 2 已完成（路径继承自阶段 2，不再询问用户）
**调用方式**：
```
调用 scp-full-feature-upgrade Skill
（路径已由阶段 2 提供，本阶段不再询问用户）
```
**执行内容**：8 大特性迁移（自研抬手亮屏 / 口袋 / 电梯 / 乘车 / 摇一摇 / 翻转 / 正背面防误触）
**总控默认策略（方案 A）**：新基线独有特性**全部不添加**，与旧项目保持一致
**输出**：scp-full-feature-upgrade 的终验表格（project.mk 终验 / dts.c 段终验 / sensorhub.mk 联动终验 / DRAM 终验）
**用户交互**：展示终验表格，**特别标注"新基线独有特性已采用方案 A 未添加"**，自动进入下一阶段

**总控升级完成后**，模型列出"新基线独有但未添加的特性"清单，用户可**单独**调用 `scp-full-feature-upgrade` Skill 处理想启用的特性

**终验**（完成后自动进入阶段 4）：
- [ ] 8 个特性宏迁移正确（与旧项目一致）
- [ ] dts.c 段参数一致
- [ ] sensorhub.mk ifeq + .c + .a 全部存在
- [ ] DRAM 段配置正确
- [ ] 已标注"方案 A，新基线独有特性未添加"

---

### 阶段 4：Kernel DTS 升级 [调用 mtk-sensor-dts-config]

**触发条件**：阶段 3 完成后自动进入，且新旧 kernel 路径均存在
**调用方式**：
```
调用 mtk-sensor-dts-config Skill，传入参数：
- 旧项目的完整路径 = {OLD_KERNEL_BASE_DIR}  (包含 kernel_device_modules 或 kernel-* 的父目录)
- 新基线的路径 = {NEW_ROOT}
```
**执行内容**：从旧 `tran_custom.config` + 旧 DTS 中提取配置，映射为新 DTS
**输出**：mtk-sensor-dts-config 的终验表格（附录 A 宏映射终验 / 附录 B 硬件参数终验）
**用户交互**：展示终验表格，自动进入下一阶段

**若 kernel 路径不存在**：标记 "阶段 4 Skipped: kernel 路径不存在"

**终验**（完成后自动进入阶段 5）：
- [ ] tran_custom.config → DTS 宏映射全部正确
- [ ] 旧 DTS → 新 DTS 硬件参数一致

---

### 阶段 5：vendor/transsion/projects 升级 [调用 tranprojects-upgrade]

**触发条件**：阶段 4 完成（或 Skipped），且 vendor/transsion/projects 路径存在
**调用方式**：
```
调用 tranprojects-upgrade Skill，传入参数：
- 旧项目根目录路径 = {OLD_ROOT}
- 新项目根目录路径 = {NEW_ROOT}
```
**执行内容**：device-vext.mk / ProjectConfig.mk / sensor_config.json 迁移
**输出**：tranprojects-upgrade 的终验表格（ProjectConfig.mk 终验 / device-vext.mk 属性终验）
**用户交互**：展示终验表格，自动进入下一阶段

**若 tranprojects 路径不存在**：标记 "阶段 5 Skipped: vendor/transsion/projects 路径不存在"

**终验**（完成后自动进入阶段 6）：
- [ ] ProjectConfig.mk 宏与旧项目一致
- [ ] device-vext.mk 属性完整迁移
- [ ] sensor_config.json 已创建且光感类型正确

---

### 阶段 6：全量验证 [调用 scp-sensor-check]

**触发条件**：阶段 5 完成（或 Skipped），且新 SCP 项目路径存在
**调用方式**：
```
调用 scp-sensor-check Skill，传入参数：
- 项目根目录路径 = {NEW_PROJECT_DIR}（或 {NEW_SCP_DIR}）
```
**执行内容**：9 段结构验证报告（宏定义 / 语法 / platform.mk 覆盖 / 驱动关联 / DTS / 库依赖 / 辅助配置 / 问题汇总 / 整体评估）
**输出**：P1/P2/P3 问题清单
**用户交互**：展示验证报告，自动进入下一阶段

**终验**（完成后自动进入阶段 7）：
- [ ] 无 P1 问题（或 P1 已自动修复）
- [ ] P2/P3 问题已列出并报告给用户

---

### 阶段 7：LID 检查 [调用 lid-check]

**触发条件**：阶段 6 完成，且新 cgen 路径存在
**调用方式**：
```
调用 lid-check Skill，传入参数：
- 项目路径 = {NEW_CGEN_INC_DIR}  (即 {NEW_ROOT}/vendor/mediatek/proprietary/custom/{PROJECT}/cgen/inc/)
```
**执行内容**：Custom_NvRam_LID.h 枚举与 CFG_file_info_custom.h 数组比对
**输出**：LID 一致性报告（逐对对应关系 + 检查结论）
**用户交互**：展示 LID 检查报告，自动进入下一阶段

**若 cgen 路径不存在**：标记 "阶段 7 Skipped: cgen 路径不存在"

**终验**（完成后进入阶段 8）：
- [ ] 枚举与数组一一对应
- [ ] 顺序一致
- [ ] 无缺漏

---

### 阶段 8：总控终验 [模型自主执行]

**触发条件**：阶段 7 完成（或 Skipped）
**操作**：汇总所有阶段的终验结果
**输出**：

```markdown
## MTK Sensorhub 3.0 全量升级 — 总控终验报告

### 阶段执行摘要
| 阶段 | 名称 | 状态 | 说明 |
|------|------|:--:|------|
| 1 | 路径推导 | ✅/⚠️/❌ | |
| 2 | SCP 基础升级 | ✅/⚠️/❌ | |
| 3 | SCP 8大特性升级 | ✅/⚠️/❌ | |
| 4 | Kernel DTS 升级 | ✅/⚠️/Skipped | |
| 5 | vendor/transsion/projects 升级 | ✅/⚠️/Skipped | |
| 6 | 全量验证 | ✅/⚠️/❌ | P1=0 / P2=N / P3=N |
| 7 | LID 检查 | ✅/⚠️/Skipped | |

### 各阶段终验链接
- 阶段 2 终验: [scp-upgrade 终验表]
- 阶段 3 终验: [scp-full-feature-upgrade 终验表]
- 阶段 4 终验: [mtk-sensor-dts-config 终验表]
- 阶段 5 终验: [tranprojects-upgrade 终验表]
- 阶段 6 终验: [scp-sensor-check 验证报告]
- 阶段 7 终验: [lid-check 检查报告]

### 整体评估
[通过 / 有条件通过 / 不通过 + 原因]
```

**终验规则**：
- 所有非 Skipped 阶段的最后一列全部 ✅ → **通过**
- 任一非 Skipped 阶段有 ❌ → **不通过**，必须先修复
- 不要总结为"已升级完成"，必须展示完整总控终验报告

---

## 常见问题

### Q1：某子模块路径推导失败怎么办？
**解决**：在路径定位表中标记 ⚠️，该阶段标记为 "Skipped"，继续执行其他阶段。报告给用户哪些阶段被跳过及原因。

### Q2：用户只想升级部分模块怎么办？
**解决**：目前全量升级是自动串行执行的。如果某模块路径不存在会自动 Skipped。如需跳过特定阶段，目前不支持。

### Q3：阶段执行中发现问题想回退怎么办？
**解决**：阶段间不响应"回退"指令。总控终验完成后，用户可要求重新执行特定阶段（如 scp-upgrade），模型重新调用对应子 Skill。

### Q4：新旧项目根目录命名不一致怎么办？
**解决**：模型以**旧项目**的 PROJECT 目录名为基准，在新项目中搜索同名目录。若找不到，列出新项目中所有候选 PROJECT 目录供用户选择。

### Q5：多个 kernel_device_modules 版本怎么办？
**解决**：Glob 搜索 `kernel/kernel_device_modules-*`，取版本号最高的目录。若有多个版本号相同的目录，列出候选供用户选择。

---

## 🎯 快速检查清单（模型自查用）

在每个阶段执行前，模型必须自问：
- [ ] 我是否已经从用户处获得了 2 项必要信息（旧/新项目根目录）？
- [ ] 我是否用 Glob 工具**实际推导**了所有子模块路径，而非假设？
- [ ] 我是否展示了路径定位表并自动进入了阶段 2？
- [ ] 我是否按依赖顺序串行执行阶段（不并行、不跳过）？
- [ ] 我是否避免了向用户询问可从代码/目录结构中获取的细节？
- [ ] 我是否在调用子 Skill 前传递了正确的路径参数？
- [ ] 我是否在每阶段完成后展示了终验表格并自动进入下一阶段？
- [ ] 我是否正确处理了 Skipped 阶段（标记原因、继续后续阶段）？
- [ ] 我是否在阶段 8 汇总了所有阶段的终验结果？
- [ ] 我是否避免了总结为"已完成"而没有展示完整终验报告？

**如果以上任何一题答案为"否"，立即停止并修正！**

---

## 🛑 强制终验表格（不可跳过）

**此表格必须在所有阶段完成后逐行填写，不可省略。**

### 阶段执行摘要

| 阶段 | 名称 | 调用 Skill | 状态 | 说明 |
|------|------|-----------|:--:|------|
| 1 | 路径推导 | —（模型自主） | ✅/⚠️/❌ | |
| 2 | SCP 基础升级 | scp-upgrade | ✅/⚠️/❌ | |
| 3 | SCP 8大特性升级 | scp-full-feature-upgrade | ✅/⚠️/❌ | |
| 4 | Kernel DTS 升级 | mtk-sensor-dts-config | ✅/⚠️/Skipped | |
| 5 | vendor/transsion/projects 升级 | tranprojects-upgrade | ✅/⚠️/Skipped | |
| 6 | 全量验证 | scp-sensor-check | ✅/⚠️/❌ | P1= / P2= / P3= |
| 7 | LID 检查 | lid-check | ✅/⚠️/Skipped | |

### 路径推导终验

| # | 路径项 | 旧路径存在? | 新路径存在? | 推导成功? | 备注 |
|---|--------|:--:|:--:|:--:|------|
| 1 | SCP_DIR | ✅/❌ | ✅/❌ | ✅/❌ | |
| 2 | PROCESSOR | — | — | ✅/❌ | |
| 3 | PLATFORM | — | — | ✅/❌ | |
| 4 | PROJECT | — | — | ✅/❌ | |
| 5 | kernel_device_modules (旧) | ✅/❌ | — | ✅/❌ | 方案A或B |
| 6 | kernel_device_modules (新) | — | ✅/❌ | ✅/❌ | |
| 7 | vendor/transsion/projects (旧) | ✅/❌ | — | ✅/❌ | 方案A/B/C |
| 8 | vendor/transsion/projects (新) | — | ✅/❌ | ✅/❌ | |
| 9 | cgen | ✅/❌ | ✅/❌ | ✅/❌ | |

### 子 Skill 终验结果汇总

| # | Skill | 终验表格已填写? | 全部 ✅? | 备注 |
|---|-------|:--:|:--:|------|
| 1 | scp-upgrade | ✅/❌ | ✅/❌ | |
| 2 | scp-full-feature-upgrade | ✅/❌ | ✅/❌ | |
| 3 | mtk-sensor-dts-config | ✅/❌ | ✅/❌ | Skipped=N/A |
| 4 | tranprojects-upgrade | ✅/❌ | ✅/❌ | Skipped=N/A |
| 5 | scp-sensor-check | ✅/❌ | ✅/❌ | |
| 6 | lid-check | ✅/❌ | ✅/❌ | Skipped=N/A |

**终验规则**：
- 所有非 Skipped 阶段的"状态"列全部 ✅ 且"全部 ✅?"列全部 ✅ → **通过**
- 如有 ❌，必须先修复才能宣告完成
- 不要总结为"已升级完成"，必须展示完整总控终验报告
