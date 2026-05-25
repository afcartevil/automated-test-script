---
name: power-display-double-tap-wake
description: "双击亮屏异常分析: 灭屏状态下双击屏幕亮屏过程中出现的异常分析，包括手势识别、口袋模式检测、传感器注册等 | 双击亮屏/双击/double tap/手势亮屏/双击无法亮屏/双击不亮/灭屏双击 | 当用户报告与「双击亮屏异常分析」相关的日志分析需求时使用"
---

# 双击亮屏异常分析

## 适用范围

- 灭屏双击不亮屏（必现/偶现）
- 双击亮屏延迟明显或需要多次
- 双击误触发（口袋中也亮屏）
- 双击触发了手势但亮屏链路未完成

---

## 不适用场景

- Power 键亮屏异常：优先 `power-display-power-key-screen`
- 通知亮屏异常：优先 `power-display-notification-wake`
- 接近/遮挡/口袋模式导致的亮屏异常：若是通话场景优先 `power-sensor-proximity-brightness`

---

## 前置条件

### 必需日志

- `bugreport*.txt`
- `mainlogcat-log*`
- `main_log*`
- `sys_log*`
- `systemlogcat-log*`
- `0-android_main.log*`
- `0-android_system.log*`

## 分析步骤

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| 手势键未上报/未被接收 | Step 1 缺失 | 排查手势开关、输入/驱动、WindowManager 拦截 |
| 口袋模式误判导致拦截 | Step 3 为 true | 复现时验证是否遮挡；排查 proximity/姿态传感器数据 |
| 亮屏链路被阻塞 | Step 4 无 unblocked | 输出阻塞断点，建议扩大时间窗并接力排查阻塞源 |
| reason 异常覆盖 | Step 5 reason 不合理 | 排查 override/省电/策略覆盖来源 |

---

---

## 分析前的最小证据集

- 是否开启“双击亮屏”功能开关
- 发生时间点（分钟级）
- 发生环境：是否在口袋/桌面、是否靠近遮挡（口袋模式关键）
- 电量/省电状态（部分策略会限制）
- 是否可复现、DUT/REF 是否一致

---

## 快速判断（是否命中双击亮屏链路）

典型信号：

- 手势键 keyCode=355：
  - `WindowManager.*interceptKeyBeforeQueueing keyCode = 355`
  - `WindowManager.*KEY_FOR_GESTURE`
- 口袋模式相关：
  - `TranPocketModeController.*doubleTapWakePocketModeListener`
  - `TranDoubleTapGesture.*onPocketModeChanged`
  - `SensorManager.*TranPocketModeController` / `SensorService.*TranPocketModeController`
- 亮屏链路：
  - `DisplayPowerController[0].*animateScreenBrightness`
  - `DisplayPowerController[0].*Unblocked screen on`

---

## 标准处理流程

### Step 1：检查手势键是否被接收（`check_gesture_key`）

- **目标**：确认 keyCode=355 的 down+up 都被 WindowManager 接收。
- **关键证据**：
  - `WindowManager.*interceptKeyBeforeQueueing keyCode = 355`
  - `WindowManager.*KEY_FOR_GESTURE`
- **判断分支**：
  - 若无：偏输入/驱动/手势层（不是 DisplayPowerController 问题）
  - 若有：进入 Step 2

### Step 2：检查口袋模式传感器是否正确注册（`check_pocket_mode_sensor`）

- **目标**：确认 PROXIMITY/HEAD_POSTURE 等口袋模式传感器注册与注销正确。
- **关键证据**：
  - `SensorManager.*TranPocketModeController`
  - `SensorService.*TranPocketModeController`
- **判断分支**：
  - 若未注册或异常：口袋模式判定不可信，可能导致误拦截或误放行
  - 正常：进入 Step 3

### Step 3：检查口袋模式判定结果（`check_pocket_mode_result`）

- **目标**：确认 `onPocketModeChanged` 为 false（非口袋中）才能允许亮屏。
- **关键证据**：`TranDoubleTapGesture.*onPocketModeChanged`
- **判断分支**：
  - 若为 true：属于“被口袋模式拦截”类问题，需解释为何判定为口袋中
  - 若为 false：进入 Step 4

### Step 4：检查亮屏链路是否完成（`check_screen_on`）

- **目标**：确认亮度动画与 Unblocked screen on 完成，表明亮屏流程走通。
- **关键证据**：
  - `DisplayPowerController[0].*animateScreenBrightness`
  - `DisplayPowerController[0].*Unblocked screen on`
- **判断分支**：
  - 有 animate 但无 unblocked：可能被阻塞/超时
  - 两者都有但仍黑屏：需要结合背光写入证据（本文 match_patterns）

### Step 5：检查亮度 reason 切换是否合理（`check_brightness_reason`）

- **目标**：确认 reason 从 screen_off → manual → automatic 的切换序列合理，避免被异常 reason 覆盖。
- **关键证据**：`DisplayPowerController[0].*reason`

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| 手势键未上报/未被接收 | Step 1 缺失 | 排查手势开关、输入/驱动、WindowManager 拦截 |
| 口袋模式误判导致拦截 | Step 3 为 true | 复现时验证是否遮挡；排查 proximity/姿态传感器数据 |
| 亮屏链路被阻塞 | Step 4 无 unblocked | 输出阻塞断点，建议扩大时间窗并接力排查阻塞源 |
| reason 异常覆盖 | Step 5 reason 不合理 | 排查 override/省电/策略覆盖来源 |

---

## 常用回答动作

- 让用户确认双击亮屏开关是否开启
- 让用户说明复现时是否在口袋/遮挡环境
- 缺少时间点：先索取时间点并扩大日志时间窗

---

## 失败时的降级策略

1. 明确卡在：手势键接收 / 口袋模式传感器 / 判定结果 / 亮屏链路 哪一层
2. 列出缺失证据与最小验证动作
3. 必要时接力到手势/输入/传感器链路团队
