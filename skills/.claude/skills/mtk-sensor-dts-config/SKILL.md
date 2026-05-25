---
name: "mtk-sensor-dts-config"
description: "根据MTK Sensor 3.0 DTS配置文档，指导新项目完成sensor_cust和irtx_pwm节点的DTS配置。⚠️ MANDATORY: 必须先从用户处获取新/旧项目路径后才能执行。Invoke when 新项目需要完成sensor DTS配置，或从老基线升级sensor DTS配置时调用。"
---

# MTK Sensor 3.0 DTS 配置指南

## ⛔ 强制执行规则（MUST READ FIRST）

**🚨 这些规则优先级最高，违反任何一条都将导致任务失败：**

### 规则 1：必须先询问，禁止自行假设
- ❌ **FORBIDDEN**: 不要假设旧项目路径、新基线路径、项目代号、光感类型等任何信息
- ✅ **REQUIRED**: 在步骤1中一次性向用户收集所有必要信息，禁止跳过任一必填项
- 🛑 **STOP**: 如果用户未提供必要信息，立即停止并询问，不要猜测或使用默认值

### 规则 2：以旧项目为准，以文档属性表为参考
- 所有 DTS 属性值必须从**旧项目 `tran_custom.config`** 中读取
- Skill 附录中的属性表仅作为**参考映射**，不作为配置值来源
- 如果旧项目宏配置与属性表示例不同，**以旧项目为准**

### 规则 3：先收集后执行（Collect-then-Execute）
- 在单一交互中**一次性收集所有必要信息**，然后自动完成分析
- 分析完成后展示修改计划，**仅需一次用户确认**即可批量执行写入
- 用户有权在任何时候修改、拒绝或补充信息

### 规则 4：一对多宏映射必须全部同步
- 某些宏（如 `CONFIG_TRAN_GET_BRIGHTNESS_LEVEL_SUPPORT`）对应**多个** DTS 属性
- 宏 `=y` → 所有对应属性都设为 `<1>`
- 宏未定义 → 所有对应属性都设为 `<0>` 或删除
- ⚠️ 附录 A.1 中标注【一对多】的宏需要特别留意，不要遗漏任何一个对应属性

---

## 参考文档

**重要**：以用户提供的飞书文档作为主要参考教程：
- [AI]底软集成sensor3.0 MTK平台P1-整体：https://transsioner.feishu.cn/wiki/DE6YwDyguirlqckJc2TcKxu7nCg
- [AI]底软集成sensor3.0 MTK平台P1-dts：https://transsioner.feishu.cn/wiki/Y0cHwg7B9iCx0FknSr7cXZMRn0b

---

## 概述

本 Skill 用于协助完成 MTK Sensor 3.0 平台新项目的 DTS 配置，将旧项目 `tran_custom.config` 中的宏映射为新基线 DTS 文件中的 `&tran_sensor_cust` 和 `&irtx_pwm` 节点属性。

**升级背景**：原代码通过**宏定义**（`CONFIG_TRAN_*`）区分项目，升级后改为**解析 DTS（设备树）**的方式。因此需要从老基线 config 中读取出启用的宏，映射为新基线 DTS 中的属性配置。

**两个权威数据源**：
1. **`tran_custom.config`**：决定宏开关类属性的启用/禁用（如 `tran-charger-poll`、`tran-cwb-support` 等）
2. **旧 DTS 文件**：决定硬件相关属性的具体数值（如 `pwm_ch`、`ml_lcm_info` 等），硬件不因 kernel 版本升级而改变

"旧项目" 指升级前的项目代码根目录（如 `u0/tran_projects/x6857/x6857_h782_a1_x6857b/x6857`），其下包含 `kernel/kernel_device_modules-*` 子目录。

---

## 核心原则

1. **以飞书文档为主要参考教程**
2. **光感类型决定配置分支**：屏下光感和狭缝光感的配置策略完全不同，必须在步骤1确认
3. **不确定时先查询附录**：遇到不认识的属性或宏，先查附录A对应表，再向用户确认
4. **新 DTS 中的注释值是脏数据**：新 baseline DTS 中注释掉的属性值不可信（可能是从其他项目复制来的占位值），禁止将其作为修改依据

---

## 重要业务规则（从实践中总结）

### 1. 屏下光感 vs 狭缝光感
- **屏下光感**：需要配置 `un_als_support`、`ml_lcm_info`、`extra_ml_lcm_info`、`ml_nv_info`、`tran-cwb-support`、`tran-freeze-detect-support`
- **狭缝光感**：以上属性**全部不要打开**，应注释或删除
- 光感类型必须向用户确认

### 2. DTS 属性与宏的对应规则
- 旧项目 `tran_custom.config` 中存在对应宏 → DTS 中启用该属性
- 旧项目 config 中**没有**对应宏 → DTS 中注释或删除该属性（包括注释本身也删除，不要保留注释行）
- 不存在的宏不要保留在 DTS 中

### 3. 属性值以旧项目为准
- 宏开关类属性（如 `<1>`, `<0>`）：取决于旧项目宏是 `=y` 还是被注释
- 硬件相关属性（如 `pwm_ch`、`ml_lcm_info`、`ml_nv_info`）：从**旧 DTS** 中读取实际值
- 属性表中的示例值和模板值仅作参考，不要照抄

### 4. `un_als_support` 配置规则
- `<1 0 0 0>` 表示 ML=1 (主光感开)，MSL=0，SL=0，SSL=0
- 非折叠屏项目通常只需要 ML=1，其余位为 0
- 折叠屏项目需要根据实际配置

### 5. Sensor 类型配置
- `sensor_type` 按实际硬件配置：`<ACC MAG GYRO ALS PS SAR>`
- 值为 `0` 表示不支持该类型 sensor
- 必须从用户处确认实际 sensor 硬件组成，不可猜测

### 6. 屏下光感光学参数来源优先级
- 光学参数（`ml_lcm_info`、`extra_ml_lcm_info`、`ml_nv_info`、`nv_restore_time`）必须按以下优先级获取：
  1. **首选**：从**旧 DTS** 中的 `&tran_sensor_cust` 节点读取实际值
  2. **次选**：用户手动提供
  3. **兜底**：暂停并询问用户
- ⛔ **严禁使用新 DTS 中注释掉的占位值**（如 `<829 45 59 59>`），这些值是从其他项目复制来的脏数据
- 当旧 DTS 中也不存在某光学属性时，不要在新 DTS 中创建该属性

### 7. irtx_pwm 硬件配置以旧 DTS 为准
- `pwm_ch`（PWM 通道号）、`ir-power` 等是硬件连线决定的，升级前后硬件不变
- 这些属性的值必须从**旧 DTS** 中的 `&irtx_pwm` 节点读取，不要沿用新 baseline 中的值
- 新 baseline DTS 中可能包含了不同项目的默认值，不可直接信任

---

## 升级流程

**流程概述**：信息收集（1次交互）→ 双源分析（自动）→ 计划文件输出 + 用户确认（1次交互）→ 执行写入 + 终验

---

### 🛑 步骤 1：一次性收集所有信息 [需要用户输入]

#### ⚠️ 执行前置条件（REQUIRED）
**在开始操作之前，必须先从用户处一次性获取以下全部信息：**
- [ ] 旧项目的完整路径（项目根目录，非 kernel 子目录）
- [ ] 新基线的路径（或告知 od_A14 / od_A16 等）
- [ ] 项目代号/名称（如 `lj6_h897`、`x6857_h782` 等）
- [ ] 光感类型：屏下光感 还是 狭缝光感
- [ ] sensor 硬件组成：ACC/MAG/GYRO/ALS/PS/SAR 各自的启用情况（启用/不支持）
- [ ] 如果为屏下光感：光学参数（可先选"稍后从旧项目读取"）

**如果用户未提供上述任何一项信息，立即停止并询问用户！不要猜测路径或光感类型！**

#### 操作
定位以下文件路径：
1. 旧项目宏控：`<旧项目>/kernel/kernel_device_modules-*/kernel/configs/tran_custom.config`
2. 新基线 DTS：`<新基线>/kernel/kernel_device_modules-*/arch/arm64/boot/dts/mediatek/<项目>.dts`
3. 旧 DTS：如果旧项目路径下有 `kernel-*/arch/arm64/boot/dts/mediatek/<项目>.dts`，一并定位

#### ✅ 确认门控
**🔴 用户确认信息完整后，立即进入自动分析阶段。**

---

### 🛑 步骤 2：自动分析（无需用户交互）

收集信息确认后，**连续自动执行**以下操作，不要逐一等待用户：

**异常处理**：
- 若 `tran_custom.config` 不存在 → 向用户报告并询问正确路径，不猜测
- 若新基线 DTS 文件不存在 → 向用户报告并询问正确项目代号，不猜测
- 若 config 中包含附录A未列出的 `CONFIG_TRAN_*` 宏 → 记录并在步骤3中告知用户
- 若旧 DTS 不存在 → 光学参数需由用户提供，不可使用新 DTS 注释值

#### 2.1 双源读取（2个权威来源）

**源1 — 新基线 DTS**：检查 `&tran_sensor_cust` 和 `&irtx_pwm` 节点是否存在，记录当前所有属性值。注意：注释掉的值仅作为"存在哪些属性"的参考，**其数值不可信**。

**源2 — 旧 DTS**：读取旧 DTS 中 `&tran_sensor_cust` 和 `&irtx_pwm` 节点的实际值。重点关注：
- 硬件相关属性：`pwm_ch`、`ir-power`、`un_als_support`、`ml_lcm_info`、`ml_nv_info`、`nv_restore_time`、`extra_ml_lcm_info`
- 这些值即为修改后的目标值（硬件不变原则）

#### 2.2 读取老基线宏控
读取 `tran_custom.config`，逐条检查以下宏的启用状态：

```
CONFIG_TRAN_GET_BRIGHTNESS_LEVEL_SUPPORT  CONFIG_TRAN_CHARGER_POLL
CONFIG_TRAN_GET_VREFRESH_SUPPORT          CONFIG_TRAN_GET_HALL
CONFIG_TRAN_CLOUD_TRACKING_SENSOR_DATA    CONFIG_TRAN_SAR_DEBUG
CONFIG_TRAN_SENSOR_DEBUG                  CONFIG_TRAN_CWB_SUPPORT
CONFIG_TRAN_FREEZE_DETECT_SUPPORT         CONFIG_TRAN_TNEK_SUPPORT
CONFIG_SENSOR_GET_LCM_INFO
```

⚠️ 注意：`CONFIG_TRAN_GET_BRIGHTNESS_LEVEL_SUPPORT` 是【一对多】宏，对应 2 个 DTS 属性，两个都必须同步处理。

#### 2.3 生成修改计划
根据宏状态和光感类型，生成修改计划。**当修改条目超过 8 条时，将计划写入文件而非仅在对话框中展示。**

计划内容包括：

| 状态 | DTS 属性 | 旧值 | 新值 | 依据 |
|------|---------|------|------|------|
| ✅ 保持 | `tran-xxx` | `<1>` | `<1>` | 旧项目宏已启用 |
| 值修改 | `tran-yyy` | `<0>` | `<1>` | 旧项目宏=y，DTS需同步 |
| 取消注释 | `tran-zzz` | 注释 | `<1>` | 宏已启用但DTS被注释 |
| ❌ 删除 | `tran-www` | 注释行 | 删除 | 旧项目无此宏，不保留 |

同时，根据光感类型处理：
- **屏下光感**：从**旧 DTS** 读取 `un_als_support`、`ml_lcm_info`、`extra_ml_lcm_info`、`ml_nv_info`、`nv_restore_time`。若旧 DTS 中某属性不存在，也不要在新 DTS 中创建（保持旧项目的实际配置）。若旧 DTS 不存在，暂停并询问用户。
- **狭缝光感**：列出需要注释/删除的屏下光感属性

- **sensor_type**：使用步骤1收集的传感器类型，组装为 `<ACC MAG GYRO ALS PS SAR>` 格式

---

### 🛑 步骤 3：用户确认修改计划 [需要用户确认]

向用户展示步骤2生成的完整修改计划：
- 修改条目 ≤ 8 条：在对话框中以表格展示
- 修改条目 > 8 条：**写入文件**（路径为 `<新基线DTS同目录>/<项目>_sensor_upgrade_plan.txt`），在对话框中告知用户文件路径

**一次性等待用户确认所有修改。**

**待确认项特别说明**：
- 一对多宏映射的属性（如 `sensor-get-screen-power-state` / `tran-get-brightness-level-support`）：如果用户质疑，引用规则4说明"同一宏对应多个属性，必须全部同步"
- 硬件相关属性值（如 `pwm_ch`、`ml_lcm_info`）：如果新老 DTS 值不同，明确标注"旧DTS值"vs"新基线默认值"，并说明"硬件不变，以旧DTS为准"

#### ✅ 确认门控
**🔴 必须等待用户确认后才能执行写入：**
- [ ] 用户确认整体修改计划
- [ ] 用户补充或更正任何属性值
- [ ] 用户明确表示"执行写入"

**只有用户确认后，才能修改 DTS 文件。**

---

### 🛑 步骤 4：执行写入并终验（自动执行）

用户确认后，**连续自动执行**：

#### 4.1 写入
使用文件编辑方法逐一修改 DTS 文件中的属性行。修改完成后删除临时的 plan 文件。

#### 4.2 终验
修改完成后重新读取文件，逐项确认：

| # | 检查项 |
|---|--------|
| 1 | `&tran_sensor_cust` 节点配置完整 |
| 2 | `&irtx_pwm` 节点配置正确 |
| 3 | 旧项目未启用的宏对应属性已删除（非仅注释） |
| 4 | 屏下光感：已配置 un_als_support / ml_lcm_info / 等 |
| 5 | 狭缝光感：已注释屏下光感相关属性 |
| 6 | `sensor_type` 按实际硬件 |
| 7 | 一对多宏映射的属性全部同步（如 sensor-get-screen-power-state 和 tran-get-brightness-level-support 状态一致） |
| 8 | 硬件相关属性值使用旧 DTS 值（pwm_ch、ml_lcm_info 等） |

#### 输出
向用户展示终验结果 —— 全部通过或指出具体问题。

---

## 附录 A：DTS 属性与宏对应关系表

### A.1 tran_sensor_cust 通用属性

| DTS 属性 | 对应宏 | 说明 |
|---------|--------|------|
| `sensor-get-screen-power-state` | `CONFIG_TRAN_GET_BRIGHTNESS_LEVEL_SUPPORT` 【一对多】 | 屏下光感需要的屏幕亮灭状态 |
| `tran-get-brightness-level-support` | `CONFIG_TRAN_GET_BRIGHTNESS_LEVEL_SUPPORT` 【一对多】 | 背光亮度等级传递 |
| `tran-charger-poll` | `CONFIG_TRAN_CHARGER_POLL` | 指南针调试充电电流传递 |
| `tran-get-vrefresh-support` | `CONFIG_TRAN_GET_VREFRESH_SUPPORT` | 刷新率传递 |
| `tran-get-hall` | `CONFIG_TRAN_GET_HALL` | hall状态传递 |
| `tran-cloud-tracking-sensor-data` | `CONFIG_TRAN_CLOUD_TRACKING_SENSOR_DATA` | 云控 |
| `tran-sar-debug` | `CONFIG_TRAN_SAR_DEBUG` | SAR feature |
| `tran-sensor-debug` | `CONFIG_TRAN_SENSOR_DEBUG` | sensor客制化log |
| `tran-cwb-support` | `CONFIG_TRAN_CWB_SUPPORT` | CWB（色温平衡）支持 |
| `tran-freeze-detect-support` | `CONFIG_TRAN_FREEZE_DETECT_SUPPORT` | 冻结检测支持 |
| `tran-tnek-support` | `CONFIG_TRAN_TNEK_SUPPORT` | - |
| `tran-lcm-supplier-info-support` | `CONFIG_SENSOR_GET_LCM_INFO` | LCM供应商信息 |
| `tran-disp-notif-support` | - | 多供屏幕参数传递 |

### A.2 屏下光感抠图参数（`un_als_support`）

```
un_als_support = <1 0 0 0>; /*ML MSL SL SSL*/
```

| 位 | 含义 | 说明 |
|---|------|------|
| ML | Main Light | 主屏幕光感开启 |
| MSL | Main Sub Light | 主屏副光感 |
| SL | Sub Light | 折叠屏内屏主光感（横向折叠机型）|
| SSL | Sub Sub Light | 折叠屏内屏副光感（横向折叠机型）|

### A.3 LCM 信息配置

```dts
/* 主传感器LCM信息 */
ml_lcm_info = <offset_x offset_y clip_w clip_h>;

/* IC感光区参数 */
extra_ml_lcm_info = <ic_x ic_y ic_w ic_h ic_in_ratio ic_out_ratio>;

/* NV信息 */
ml_nv_info = <vendortype algotype version>;

/* NV恢复时间（秒） */
nv_restore_time = <3>;
```

**⚠️ 以上具体数值必须从旧 DTS 实际值获取，禁止使用新 DTS 中注释的占位值！**
**⚠️ 若旧 DTS 中不存在 `extra_ml_lcm_info`，则新 DTS 中也不要创建该属性。**

### A.4 Sensor 类型配置

```dts
/* ACC-1 MAG-2 GYRO-4 ALS-5 PS-8 SAR-25 no_support-0 */
sensor_type = <1 2 4 5 8 0>;
```

### A.5 irtx_pwm 红外节点

```dts
&irtx_pwm {
    pwm_ch = <1>;           // PWM通道编号 — 从旧DTS读取，硬件不变
    status = "okay";        // 设备状态
    ir-power = "vbat";      // 红外发射电源 — 从旧DTS读取
};
```

**⚠️ `pwm_ch` 和 `ir-power` 是硬件决定的，必须从旧 DTS 读取实际值。硬件不随 kernel 版本升级而改变。**

### A.6 `&tran_sensor_cust` 节点模板（用于节点缺失场景）

当步骤2发现 DTS 中缺少 `&tran_sensor_cust` 节点时，可使用以下模板添加。**模板中的值仅作为格式参考，实际值必须根据步骤2分析结果填入。**

```dts
&tran_sensor_cust {
    sensor-get-screen-power-state = <0>;
    tran-charger-poll = <0>;
    tran-get-brightness-level-support = <1>;
    tran-get-vrefresh-support = <1>;
    tran-get-hall = <0>;
    tran-cloud-tracking-sensor-data = <0>;
    tran-sar-debug = <0>;
    tran-sensor-debug = <0>;
    // ... 其余属性根据步骤2分析结果补充
    sensor_type = <1 2 4 5 8 0>;
};

&irtx_pwm {
    pwm_ch = <2>;           // ⚠️ 此为模板占位值，实际必须从旧DTS读取
    status = "okay";
    ir-power = "vbat";
};
```

---

## 附录 B：狭缝光感项目（不需要打开的属性）

如果项目为**狭缝光感**（非屏下光感），以下属性**都不需要打开**，应注释或删除：

```dts
    //tran-cwb-support = <1>;
    //tran-freeze-detect-support = <1>;
    //tran-tnek-support = <0>;
    //un_als_support = <1 0 0 0>;
    //ml_lcm_info = <...>;
    //extra_ml_lcm_info = <...>;
    //ml_nv_info = <...>;
```

---

## 常见问题

### DTS 修改后编译失败
- **原因**：属性格式错误或节点引用不存在
- **解决**：检查属性值格式（尖括号、引号），确认 `&tran_sensor_cust` 和 `&irtx_pwm` 节点在 dtsi 中有定义

### 找不到 tran_custom.config
- **原因**：旧项目路径不正确或文件位于其他位置
- **排查**：通常路径为 `<旧项目>/kernel/kernel_device_modules-*/kernel/configs/tran_custom.config`，可搜索 `find . -name "tran_custom.config"`

### 属性已注释但仍出现在 DTS 中
- **原则**：如果旧项目 config 中某个宏未启用，但 DTS 中对应的属性未被删除、仅被注释保留，这种"注释保留"的做法不推荐——应直接删除整行，以免误导后续维护者。

### 新 DTS 中注释值不可信
- **现象**：新 baseline DTS 中注释掉的属性值（如 `//ml_lcm_info = <829 45 59 59>;`）可能与旧项目旧 DTS 中的实际值（如 `<843 63 43 43>`）不一致
- **原因**：新 baseline 可能是从其他项目模板复制而来，注释值只是占位符或旧项目的脏数据
- **原则**：光学参数等硬件相关值**必须从旧 DTS 读取**，永远不要使用新 DTS 中注释掉的值

### sensor-get-screen-power-state 和 tran-get-brightness-level-support 的关系
- 两者都对应同一个宏 `CONFIG_TRAN_GET_BRIGHTNESS_LEVEL_SUPPORT`，但传递不同数据：
  - `sensor-get-screen-power-state`：屏幕亮/灭状态（布尔）
  - `tran-get-brightness-level-support`：屏幕亮度值 0-4095（数值）
- 当宏 `=y` 时，两者都应设为 `<1>`；宏未定义时，两者都应设为 `<0>` 或删除

---

## 🎯 快速检查清单（模型自查用）

在关键节点，模型必须自问：
- [ ] 我是否在步骤1一次性向用户收集了所有必要信息（路径、代号、光感类型、sensor硬件组成）？
- [ ] 我是否从旧项目的 `tran_custom.config` 实际读取了宏状态？
- [ ] 我是否同时读取了旧 DTS 中的 `&tran_sensor_cust` 和 `&irtx_pwm` 节点值？
- [ ] 我是否检查了附录 A.1 中标注【一对多】的宏，确保所有对应属性都已同步处理？
- [ ] 我是否避免了使用新 DTS 注释中的占位值作为修改依据？
- [ ] 硬件相关属性（pwm_ch、ml_lcm_info 等）是否来自旧 DTS 实际值？
- [ ] 我是否根据光感类型（屏下 vs 狭缝）正确处理了屏下光感相关属性？
- [ ] 我是否在步骤3向用户展示了完整修改计划并获得了确认？
- [ ] 写入后是否重新读取文件进行了终验？
- [ ] 终验时是否检查了一对多宏映射的属性状态一致性？

**如果以上任何一题答案为"否"，立即停止并修正！**
