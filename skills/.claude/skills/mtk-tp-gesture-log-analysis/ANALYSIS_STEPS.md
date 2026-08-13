# 详细分析步骤

## 分析流程概览

按 SOP 固定顺序执行：

1. 获取日志
2. 过滤 TP 手势关键日志
3. 分析 `kernel_log`
4. 分析 `main_log` / `sys_log`

只有在 TP 侧链路确认正常后，才能把问题继续收敛到 framework 或其他模块。

## 步骤1：获取日志

### 目标

确认当前输入中已包含可用于 TP 手势分析的有效日志。

### 操作

1. 如果用户给的是 JIRA 号、目录、压缩包或文件夹，先定位可分析日志。
2. 排除与 TP 领域无关的日志，仅保留串口日志、`kernel_log`、Android 日志等。
3. 若存在 `mobilelog` 文件夹，优先读取其中的 `kernel_log` 和 `main_log`。
4. 若存在 `mobilelog` 文件夹，开机阶段相关日志优先查看其子文件夹 `booot_normal`。

### 判断条件

| 条件 | 结论 | 下一步 |
|---|---|---|
| 获取日志失败 | 无法继续分析 | 停止分析并明确缺失日志 |
| 获取日志成功 | 满足分析前提 | 进入步骤2 |

## 步骤2：日志过滤

### 目标

从大日志中筛出 TP 手势主链路相关内容。

### 操作

1. 在 `kernel_log` 中搜索：`touch|fts|cts|gtp|nvt|chsc|ilitek|tcm`
2. 在 `main_log`、`sys_log` 中搜索：`KeyguardGesture|keycode`
3. 保留驱动加载、模式切换、手势使能、手势上报、framework 接收与处理等关键片段。

### 判断条件

| 条件 | 结论 | 下一步 |
|---|---|---|
| 完成 `kernel_log`、`main_log`、`sys_log` 关键日志过滤 | 可以进入主链路分析 | 进入步骤3 |

## 步骤3：分析 `kernel_log`

### 目标

确认 TP 驱动是否正常工作，手势功能是否开启，亮灭屏模式切换是否正确，以及 TP 手势键值是否成功上报。

### 3.1 检查 TP 驱动是否正常工作

**操作**：

1. 搜索 TP 驱动加载日志。
2. 重点查看：
   - `bootmode is 0`
   - `support_ic`
   - `load main controller ... success`
3. 再查看亮屏常规触摸日志，如 `touch up`、`touch down`。

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 存在 `bootmode is 0` 且 TP IC 匹配、驱动加载成功 | TP 驱动加载正常 | 继续 3.2 |
| 未看到 TP IC 匹配或驱动加载成功日志 | 优先怀疑 TP 驱动 / 项目集成异常 | 输出 TP 侧异常结论 |

### 3.2 检查手势功能是否开启

**操作**：

1. 搜索 `gesture_data_write`
2. 重点查看是否存在以下使能日志：
   - `code1[cc] enable[1]`：双击亮屏
   - `code1[aa]` / `code1[bb]` / `code1[ab]` / `code1[ba]`：音乐手势
   - `code1[ff] enable[1]`：快速启动手势
3. 同时检查是否出现：
   - `Sorry, this gesture has been disabled.`

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 存在目标手势的 `enable[1]` 日志 | 对应手势已开启 | 继续 3.3 |
| 目标手势没有开启日志，或出现 disabled 提示 | 系统或驱动未开启该手势 / 手势未支持 | 输出手势开关异常结论 |

### 3.3 检查亮灭屏 TP 模式切换是否正确

**操作**：

1. 搜索 `state_change_machine`
2. 重点核对：
   - 亮屏：`TRAN_GESTURE_SUSPEND_MODE --> TRAN_ACTIVE_MODE`
   - 灭屏：`TRAN_ACTIVE_MODE --> TRAN_GESTURE_SUSPEND_MODE`
3. 若出现 `TRAN_ACTIVE_MODE --> TRAN_SUSPEND_MODE`，标记为异常线索。

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 灭屏进入 `TRAN_GESTURE_SUSPEND_MODE`，亮屏恢复 `TRAN_ACTIVE_MODE` | TP 模式切换正确 | 继续 3.4 |
| 灭屏进入普通 `TRAN_SUSPEND_MODE` | 系统或驱动未开启手势模式 | 输出模式切换异常结论 |

### 3.4 检查驱动是否上报 TP 手势键值

**操作**：

1. 搜索 `GestureHandle`、`GestureIdTranslate`
2. 重点查看：
   - `gesture report KEY_F26 done !`
   - 音乐手势值码，如 `g_gtp_gesture=0xab`
   - 音乐手势上报，如 `gesture report KEY_F13 done !`

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 已看到目标手势上报日志 | TP 驱动侧分析基本完成 | 进入步骤4 |
| 未看到手势上报日志 | 手势未在 TP 侧成功上报 | 输出 TP 上报异常结论 |

## 步骤4：分析 `main_log` / `sys_log`

### 目标

确认 framework 是否收到并处理 TP 手势，以及是否被口袋模式或媒体状态等上层条件拦截。

### 4.1 检查 framework 是否收到 TP 手势

**操作**：

1. 搜索 `keyCode`
2. 重点查看：
   - `interceptKeyBeforeQueueing keyCode = 355`
3. 同时确认是否进入：
   - `KeyguardGestureService: onStartCommand method=onFinishedWakingUp`
   - `KeyguardGestureService: onStartCommand method=dispatchTPGesture`

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| 收到 `keyCode = 355` 且进入 `KeyguardGestureService` | framework 已收到并开始处理手势 | 继续 4.2 |
| TP 已上报但上层未收到对应 `keyCode` | 问题位于 TP 与 framework 之间的上报链路 | 输出上层未接收结论 |

### 4.2 双击亮屏问题专项检查

**操作**：

1. 搜索 `TranDoubleTapGesture`
2. 重点查看：
   - `doubleTapWakePocketModeListener onPocketModeChanged: false`
   - `doubleTapWakePocketModeListener onPocketModeChanged: true`

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| `onPocketModeChanged: true` | 双击亮屏被口袋模式拦截，优先检查距离传感器校准 | 输出口袋模式拦截结论 |
| `onPocketModeChanged: false` 但仍不亮屏 | 双击问题不在口袋模式，继续结合其他上层处理日志判断 | 输出需进一步收敛结论 |

### 4.3 音乐手势问题专项检查

**操作**：

1. 搜索 `dispatchTPGesture`
2. 重点查看：
   - `KeyguardGestureManager: dispatchTPGesture---a[0]---= 171`
   - `KeyguardGestureManager: music gesture, check music active true, mCurrentGestrue = play_000`

**判断**：

| 条件 | 结论 | 下一步 |
|---|---|---|
| TP 已正常上报，framework 进入 `dispatchTPGesture`，但 `music active true` | 系统媒体播放状态 flag 未更新，导致播放音乐手势被拦截 | 输出 framework 状态异常结论 |
| TP 已正常上报，framework 未进入对应处理逻辑 | 继续检查上层分发路径 | 输出 framework 分发异常结论 |
