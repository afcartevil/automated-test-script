---
name: power-display-power-key-screen
description: "Power键亮灭屏异常分析: Power键按下后亮屏或灭屏过程中出现的异常分析 | power/电源键/亮屏/灭屏/黑屏/无法亮屏/无法灭屏/屏幕不亮 | 当用户报告与「Power键亮灭屏异常分析」相关的日志分析需求时使用"
funcType: "AI故障分析"
category: "功耗"
---

# Power键亮灭屏异常分析

## 适用范围

- 按电源键 **不亮屏** / 亮屏延迟明显 / 偶现失败
- 按电源键 **不灭屏** / 灭屏卡住 / 灭屏后又被拉起
- 日志显示进入 Waking/Sleeping，但显示链路未闭环（Unblocked/背光写入缺失）

---

## 不适用场景

- 到时间不灭屏（超时触发）：优先 `power-display-timeout-screen-off`
- 双击/通知等非按键触发的亮屏：优先 `power-display-double-tap-wake` / `power-display-notification-wake`
- 通话遮挡导致黑屏/亮屏：优先 `power-sensor-proximity-brightness`

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

```text
- [ ] 检查 Power 键事件是否被接收（`check_power_key`）
- [ ] 检查亮屏主流程是否闭环（`check_screen_on_flow`）
- [ ] 检查 BrightnessEvent 上报是否合理（`check_brightness_event`）
- [ ] 检查背光节点是否被正确写入（`check_backlight_write`）
- [ ] 检查灭屏主流程（`check_screen_off_flow`）
- [ ] 检查亮屏耗时是否异常（`check_screen_on_duration`）
```

---

## 分析前的最小证据集

- 发生时间点（分钟级），按键次数（单击/连按）
- 当时状态：锁屏/解锁、AOD/Doze、是否接近遮挡、是否在口袋
- 电量/省电/温控状态（可能影响亮屏时序）
- 是否可复现、DUT/REF 是否一致

---

## 快速判断（是否命中 Power 键链路）

典型信号：

- 按键被系统接收：
  - `TranPhoneWindowManagerImpl.*interceptKeyTq`
  - `PowerGroup.*Waking`
- 亮屏阻塞与解除：
  - `DisplayPowerController[0].*Blocking.*on`
  - `DisplayPowerController[0].*Unblocked.*on`
- 亮度动画与 reason：
  - `DisplayPowerController[0].*animateScreenBrightness`
  - `DisplayPowerController[0].*reason changing to`
- 背光写入：
  - `android.hardware.lights-service.mediatek.*/sys/class/leds/lcd-backlight/brightness`
  - `LIGHTS.*/sys/class/backlight/sprd_backlight/brightness`
- 灭屏链路：
  - `DisplayPowerController[0].*Blocking.*off`
  - `DisplayPowerController[0].*Unblocked.*off`
  - `PowerGroup.*Sleeping`

---

## 正常链路参考（用于和当前日志对比）

正常 Power 键亮灭屏链路应当能看到下面的阶段顺序。飞书里的正常打印案例只用于对比链路完整性，不能作为当前问题证据。

1. Power 键事件进入输入/窗口策略层，`interceptKeyTq` 或同类日志能看到按键被系统接收。
2. 亮屏时 `PowerGroup` 进入 Waking；灭屏时进入 Sleeping/Powering off 相关流程。
3. `DisplayPowerController` 进入对应的 Blocking on/off 阶段。
4. 第一帧/绘制完成后 Unblocked on/off 出现，说明显示电源流程解除阻塞。
5. `animateScreenBrightness` 或 BrightnessEvent 体现亮度目标变化。
6. HAL / backlight 写入与亮屏或灭屏目标一致。
7. 亮屏耗时类问题应能用 `Screen on took` 或关键阶段时间差定位到具体耗时段。

如果当前日志只看到按键事件但没有 Waking/Sleeping，只能定位到输入到电源状态转换之间；如果有 Waking 但没有 Unblocked，应优先分析阻塞点，不要直接归因到背光写入。

### 与飞书正常案例的对比方式

- 对比“按键接收 -> Waking/Sleeping -> Blocking -> Unblocked -> 亮度/背光写入”是否完整。
- 正常案例中的耗时只能作为参考阈值，当前慢亮屏要以当前日志时间差为准。
- 不要把正常案例中的 Unblocked 或 backlight 打印当作当前问题证据。

---

## 标准处理流程

### Step 1：检查 Power 键事件是否被接收（`check_power_key`）

- **目标**：确认按键事件进入系统拦截链路，并触发 Waking。
- **关键证据**：
  - `TranPhoneWindowManagerImpl.*interceptKeyTq`
  - `PowerGroup.*Waking`
- **判断分支**：
  - 若无：偏按键/输入链路/拦截配置问题
  - 若有：进入 Step 2

### Step 2：检查亮屏主流程是否闭环（`check_screen_on_flow`）

- **目标**：确认 “Blocking → 第一帧/绘制 → Unblocked → 亮度设置” 的关键节点都出现。
- **关键证据**：
  - `DisplayPowerController[0].*Blocking.*on`
  - `DisplayPowerController[0].*Unblocked.*on`
  - `DisplayPowerController[0].*animateScreenBrightness`
- **判断分支**：
  - Blocking 出现但 Unblocked 缺失：属于“亮屏被阻塞/卡住”类
  - animate 有但背光无：进入 Step 4 确认写入链路

### Step 3：检查 BrightnessEvent 上报是否合理（`check_brightness_event`）

- **目标**：确认状态与亮度事件上报正常，避免“上层认为亮了但实际未亮”。
- **关键证据**：`DisplayPowerController[0].*BrightnessEvent`

### Step 4：检查背光节点是否被正确写入（`check_backlight_write`）

- **目标**：把问题落在 Framework 目标还是 HAL/驱动实际写入。
- **关键证据**：背光节点写入日志（本文 match_patterns 已覆盖常见路径）
- **判断分支**：
  - 目标变化但写入缺失/异常：偏 HAL/驱动
  - 写入正常但仍黑屏：继续补齐合成/面板侧证据

### Step 5：检查灭屏主流程（`check_screen_off_flow`）

- **目标**：确认灭屏 “Blocking off → Unblocked off → 亮度归零 → Sleeping”。
- **关键证据**：
  - `DisplayPowerController[0].*Blocking.*off`
  - `DisplayPowerController[0].*Unblocked.*off`
  - `PowerGroup.*Sleeping`

### Step 6：检查亮屏耗时是否异常（`check_screen_on_duration`）

- **目标**：当用户描述“亮屏很慢”，用系统统计日志量化耗时。
- **关键证据**：`PowerManagerService.*Screen on took`

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| 按键事件未到达系统 | Step 1 缺失 | 排查按键驱动/拦截逻辑/开关配置 |
| 亮屏阻塞导致卡住 | Step 2 blocking 有但 unblocked 缺失 | 输出阻塞断点；扩大日志时间窗，接力排查阻塞源 |
| Framework 目标正常但写入异常 | Step 4 不一致 | 排查 lights HAL/背光节点映射/权限 |
| 亮屏耗时异常 | Step 6 显示耗时很长 | 拆解阻塞点与耗时段，提供进一步采集建议 |

---

## 常用回答动作

- 先要“按键时刻”的时间点（按下到屏幕变化）
- 让用户确认当时是否遮挡/在口袋/省电（排除策略干扰）
- 若偶现：建议重复按键 5~10 次并记录失败次数与时间点

---

## 失败时的降级策略

1. 将链路拆成：按键接收 → 亮屏阻塞/解除 → 亮度/背光写入 → 状态闭环
2. 明确当前定位到的断点与缺失证据
3. 提供最小复现与采集建议（优先 1 个）

---

## 证据约束

- 没有按键接收日志时，不能确认系统收到了 Power 键。
- 没有 Waking/Sleeping 时，不能确认电源状态机已进入亮灭屏流程。
- 有 Blocking 但没有 Unblocked 时，应优先定位阻塞阶段，不能直接归因 HAL。
- 没有 backlight 写入证据时，不能把黑屏/不亮屏确定归因到驱动写入。
- Markdown 和飞书正常案例只用于对比正常链路，不是当前问题事实。
