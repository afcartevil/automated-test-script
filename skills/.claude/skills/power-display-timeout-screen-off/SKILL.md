---
name: power-display-timeout-screen-off
description: "超时灭屏异常分析: 超过自动息屏时间后灭屏过程中出现的异常分析 | 超时灭屏/自动灭屏/timeout/自动息屏/屏幕超时/不灭屏/无法灭屏/息屏时间 | 当用户报告与「超时灭屏异常分析」相关的日志分析需求时使用"
---

# 超时灭屏异常分析

## 适用范围

- 到达设定超时时间后 **不灭屏**
- 灭屏触发但 **延迟很长**
- 灭屏过程中出现 **Blocking screen off** 长时间不解除
- 亮度动画没有降到 0 或 reason 不变为 screen_off
- `onScreenChanged false` 不出现（系统认为屏幕没关）

---

## 不适用场景

- 按电源键导致的灭屏/亮屏异常：优先 `power-display-power-key-screen`
- 通话遮挡/口袋模式触发的灭屏：优先 `power-sensor-proximity-brightness`
- 应用持有 wakelock 导致不灭屏：仍可在本场景定位“被阻塞”，但最终根因可能需要接力到持锁方

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
- [ ] 检查是否真的触发了超时事件（`check_timeout_trigger`）
- [ ] 检查 Going to sleep 参数是否符合预期（`check_going_to_sleep`）
- [ ] 检查灭屏是否被阻塞以及阻塞耗时（`check_screen_off_block`）
- [ ] 检查亮度是否归零与 reason 是否切到 screen_off（`check_brightness_zero`）
- [ ] 检查系统是否确认屏幕已关闭（`check_screen_changed`）
```

---

## 分析前的最小证据集

- 系统“屏幕超时”配置（30s/1min/2min 等）
- 发生时间点（分钟级）
- 前台应用/是否播放视频/是否充电（可能影响策略）
- 是否开启省电/Always-on/Doze（可能影响）
- 是否可复现、是否 DUT/REF 一致

---

## 快速判断（是否命中超时灭屏链路）

典型信号：

- 超时触发：
  - `PowerGroup.*Powering off`
- 进入睡眠：
  - `PowerManagerService.*Going to sleep`
- 灭屏阻塞/解除：
  - `DisplayPowerController2[0].*Blocking screen off`
  - `DisplayPowerController2[0].*Unblocked screen off`
- 亮度归零与 reason 变化：
  - `DisplayPowerController2[0].*animateScreenBrightness`
  - `DisplayPowerController2[0].*reason changing to`
- 屏幕状态回调：
  - `PowerManagerService.*onScreenChanged`

---

## 正常链路参考（用于和当前日志对比）

正常超时灭屏链路应当能看到下面的阶段顺序。飞书里的正常打印案例只用于对比链路完整性，不能作为当前问题证据。

1. 用户无操作达到系统配置的屏幕超时时间。
2. `PowerGroup` 因 timeout 触发 powering off。
3. `PowerManagerService` 进入 `Going to sleep`，参数应能对应当前 screen off timeout / activity timeout。
4. `DisplayPowerController` 进入 `Blocking screen off`。
5. 阻塞解除后出现 `Unblocked screen off`，亮度开始归零。
6. `animateScreenBrightness` / reason 体现 screen off 方向收敛。
7. `onScreenChanged false` 或同类状态回调确认屏幕关闭闭环。

如果当前日志没有 timeout 触发，不能直接判断灭屏流程异常；应先排查是否存在用户活动、wakelock、前台视频播放、充电/AOD/Doze 策略等抑制条件。

### 与飞书正常案例的对比方式

- 对比“timeout 触发 -> Going to sleep -> Blocking/Unblocked -> 亮度归零 -> 状态回调”是否完整。
- 正常案例中的超时时长只能作为参考，当前判断要以当前系统配置和当前日志时间差为准。
- 不要把正常案例中的 `onScreenChanged false` 当作当前问题已经灭屏的证据。

---

## 标准处理流程

### Step 1：检查是否真的触发了超时事件（`check_timeout_trigger`）

- **目标**：确认 PowerGroup 因 timeout 触发 powering off，并可推断超时点。
- **关键证据**：`PowerGroup.*Powering off`
- **判断分支**：
  - 若无触发：可能是一直有用户活动/持锁/策略抑制 → 需要先确认活动与持锁证据（接力方向）
  - 若有触发：进入 Step 2

### Step 2：检查 Going to sleep 参数是否符合预期（`check_going_to_sleep`）

- **目标**：确认进入 sleep 的原因与参数（screenOffTimeout / activityTimeout）与配置一致。
- **关键证据**：`PowerManagerService.*Going to sleep`
- **判断分支**：
  - 参数异常：可能配置读取/策略覆盖
  - 参数正常：进入 Step 3

### Step 3：检查灭屏是否被阻塞以及阻塞耗时（`check_screen_off_block`）

- **目标**：定位是否存在 `Blocking screen off` 长时间不解除，这是“不灭屏/延迟”的高频断点。
- **关键证据**：
  - `DisplayPowerController2[0].*Blocking screen off`
  - `DisplayPowerController2[0].*Unblocked screen off`
- **判断分支**：
  - 长时间阻塞：输出“阻塞断点”并建议接力排查阻塞源（例如窗口/动画/策略/唤醒锁相关）
  - 正常解除：进入 Step 4

### Step 4：检查亮度是否归零与 reason 是否切到 screen_off（`check_brightness_zero`）

- **目标**：确认灭屏亮度收敛到 0，以及 reason 正确变化。
- **关键证据**：
  - `DisplayPowerController2[0].*animateScreenBrightness`
  - `DisplayPowerController2[0].*reason changing to`
- **判断分支**：
  - 亮度未归零/reason 不对：偏亮度/状态机路径异常
  - 正常：进入 Step 5

### Step 5：检查系统是否确认屏幕已关闭（`check_screen_changed`）

- **目标**：确认 `onScreenChanged false` 出现，表示系统状态完成闭环。
- **关键证据**：`PowerManagerService.*onScreenChanged`
- **判断分支**：
  - 不出现：需要继续追查屏幕状态切换链路（可能仍被某处认为未关屏）

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| 超时未触发（被活动/持锁抑制） | Step 1 无 powering off | 先确认是否有持续输入/唤醒锁；收集前台与持锁证据 |
| 灭屏被阻塞 | Step 3 阻塞长时间不解除 | 输出阻塞断点，建议排查阻塞源并接力 |
| 亮度未归零/reason 不对 | Step 4 异常 | 排查 DisplayPowerController2 状态机与亮度动画 |
| 状态未闭环 | Step 5 缺失 | 继续追查屏幕状态变更链路与回调 |

---

## 常用回答动作

- 让用户提供屏幕超时配置与发生时间点
- 若阻塞明显：建议提供更长时间窗日志（覆盖超时前后）
- 若怀疑持锁：让用户提供可能的前台应用/播放/充电/省电状态

---

## 失败时的降级策略

1. 降级到“断点定位”：超时触发/进入 sleep/阻塞/亮度归零/状态闭环
2. 列出缺失证据与最小验证动作
3. 需要时接力到窗口/电源/应用持锁方向

---

## 证据约束

- 没有 timeout/powering off 触发证据时，不能确认超时灭屏链路已启动。
- 没有 `Going to sleep` 时，不能确认 PowerManagerService 已进入 sleep 流程。
- 有 Blocking 但没有 Unblocked 时，应优先定位阻塞源。
- 没有亮度归零或状态回调证据时，不能确认灭屏闭环完成。
- Markdown 和飞书正常案例只用于对比正常链路，不是当前问题事实。
