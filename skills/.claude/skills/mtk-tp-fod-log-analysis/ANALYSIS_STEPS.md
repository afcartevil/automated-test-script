# 详细分析步骤

## 分析流程概览

按 SOP 固定顺序执行：

1. 获取日志
2. 过滤 TP 与 FOD 关键日志
3. 分析灭屏、亮屏、录入场景下的 TP FOD 链路

只有在确认日志中没有 FOD 按下 / 抬起事件时，才优先将问题收敛到 TP 侧。

## 步骤1：获取日志

### 目标

确认当前输入中已包含可用于 TP 侧 FOD 录入分析的有效日志。

### 操作

1. 如果给定的是 JIRA 号、文件夹等非直接 log 文件，先获取日志文件。
2. 排除与 TP 领域无关的日志文件，只保留串口日志、`kernel_log`、Android 日志等文件。
3. 若存在 `mobilelog` 文件夹，则获取该文件夹下的 `kernel_log`。
4. 若存在 `mobilelog` 文件夹，则开机阶段相关日志优先查看子文件夹 `booot_normal`。

### 判断条件

| 条件 | 结论 | 下一步 |
|---|---|---|
| 获取日志失败 | 无法继续分析 | 停止分析 |
| 获取日志成功 | 满足分析前提 | 进入步骤2 |

## 步骤2：日志过滤

### 目标

从大日志中筛出 TP 驱动与 FOD 指纹录入主链路相关内容。

### 操作

1. 在 `kernel_log` 中搜索 TP 关键字：`touch|fts|cts|gtp|nvt|chsc|ilitek|tcm`。
2. 按 SOP 第 4 章补充搜索：`tran_fingerprint_status`。
3. 重点保留以下日志片段：
   - `fingerprint_status_write`
   - `fod finger down`
   - `fod finger up`
   - `state_change_machine`
   - `nvt_disp_notifier_callback`

### 判断条件

| 条件 | 结论 | 下一步 |
|---|---|---|
| 已筛出 TP 与 FOD 关键日志 | 可以进入链路分析 | 进入步骤3 |
| 未筛出任何 TP / FOD 关键日志 | 证据不足或日志不对口 | 停止分析并提示补充 `kernel_log` |

## 步骤3：分析日志

### 目标

确认灭屏时指纹状态写入是否正确，亮屏与录入场景下是否存在 FOD 按下 / 抬起事件，从而判断问题是否收敛到 TP 侧。

### 3.1 检查灭屏时指纹节点写入是否正确

**操作**：

1. 搜索 `fingerprint_status_write`。
2. 结合灭屏链路查看：
   - `tran_fingerprint_status = 1`
   - `drm notify tp suspends start`
   - `TRAN_ACTIVE_MODE --> TRAN_GESTURE_SUSPEND_MODE`
   - `drm notify tp suspends end`

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 存在 `tran_fingerprint_status = 1`，且 TP 正常切到 `TRAN_GESTURE_SUSPEND_MODE` | 灭屏侧状态写入与模式切换正常 | 继续 3.2 |
| 未看到 `tran_fingerprint_status = 1` 或未切到手势模式 | 灭屏 FOD 链路异常，优先怀疑 TP 状态写入或模式切换 | 输出 TP 侧异常结论 |

### 3.2 检查亮屏解锁时是否有 FOD 按下 / 抬起事件

**操作**：

1. 搜索亮屏链路中的 `resume start`、`TRAN_GESTURE_SUSPEND_MODE --> TRAN_ACTIVE_MODE`、`resume end`。
2. 在对应时间段检查：
   - `fod finger down`
   - `fod finger up`

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 亮屏恢复后存在 `fod finger down` 和 `fod finger up` | 亮屏解锁链路中的 FOD 事件上报正常 | 继续 3.3 |
| 亮屏恢复后缺少 FOD 事件 | 可能存在 TP resume 恢复或状态机异常 | 输出 TP 侧异常结论 |

### 3.3 检查设置中录入指纹时是否有 FOD 按下 / 抬起事件

**操作**：

1. 搜索录入场景中的 `tran_fingerprint_status = 2`。
2. 检查其后是否存在：
   - `touch down!`
   - `fod finger down`
   - `touch up!`
   - `fod finger up`

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 录入场景存在完整的按下 / 抬起事件 | 与 TP 无关，继续转查指纹 HAL / framework 或其他模块 | 输出非 TP 结论 |
| 录入场景没有指纹按下 / 抬起事件 | 可能与 TP 有关 | 输出 TP 侧结论 |

## 结论收敛规则

### 收敛为 TP 侧问题

满足以下现象时，可优先判断为 TP 侧：

- `tran_fingerprint_status` 未按预期写入
- TP 未正确切换 FOD / 手势模式
- 设置录入或亮屏解锁阶段没有 `fod finger down` / `fod finger up`

### 收敛为非 TP 侧问题

满足以下现象时，不应继续优先收敛到 TP：

- 录入或解锁阶段存在完整的 `fod finger down` / `fod finger up`
- TP 状态写入、模式切换、FOD 事件上报均正常

此时应继续检查指纹 HAL、framework 或其他联动模块。
