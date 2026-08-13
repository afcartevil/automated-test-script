---
name: power-display-notification-wake
description: "通知亮屏异常分析: 收到消息通知后亮屏流程中出现的异常分析，包括有效时间判断、口袋模式、唤醒流程等 | 通知亮屏/通知不亮屏/通知唤醒/消息亮屏/notification/来消息不亮/锁屏通知/消息不亮屏 | 当用户报告与「通知亮屏异常分析」相关的日志分析需求时使用"
funcType: "AI故障分析"
category: "功耗"
---

# 通知亮屏异常分析

## 适用范围

- 锁屏收到消息 **不亮屏**
- 仅部分时间段不亮（疑似“有效时间”判断）
- 口袋/遮挡情况下行为不符合预期（误拦截或误放行）
- 有唤醒日志但背光/显示模式未切换

---

## 不适用场景

- Power 键亮屏异常：优先 `power-display-power-key-screen`
- 双击亮屏异常：优先 `power-display-double-tap-wake`
- 仅应用侧不弹通知：属于应用通知策略，不在本场景范围

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
- [ ] 确认是否收到通知事件（`check_notification_received`）
- [ ] 检查有效时间与勿扰相关判断（`check_effective_time`）
- [ ] 检查是否被口袋模式拦截（`check_pocket_mode`）
- [ ] 检查系统是否真正发起唤醒（`check_wakeup`）
- [ ] 检查显示电源模式切换与背光写入（`check_display_power`）
```

---

## 分析前的最小证据集

- 通知类型：来电/短信/IM/系统通知，是否高优先级
- 锁屏状态：是否 AOD/Doze、是否熄屏
- 发生时间点（分钟级），是否集中在某个时间段
- 是否开启勿扰/夜间模式/省电
- 复现步骤：发几条通知、间隔、是否点亮过屏幕后再测

---

## 快速判断（是否命中通知亮屏链路）

典型信号：

- 通知接收：
  - `TranLockScreenNotification.*onNotificationPosted`
- 有效时间判断：
  - `TranLockScreenNotification.*isNotifyScreenOnEffectiveTime`
  - `TranLockScreenNotification.*totalNowMinutes`
- 口袋模式拦截：
  - `TranPocketModeController.*NotificationWakePocketModeListener`
- 系统唤醒：
  - `PowerManagerService.*Waking up`
- 显示电源模式与背光：
  - `TranPowerStateChangedController.*onSetDisplayPowerMode`
  - `LocalDisplayAdapter.*backlight`

---

## 正常链路参考（用于和当前日志对比）

正常通知亮屏链路应当能看到下面的阶段顺序。飞书里的正常打印案例只用于对比链路完整性，不能作为当前问题证据。

1. 通知发布到系统侧，并进入 `TranLockScreenNotification`。
2. 系统判断当前通知是否允许亮屏，包括有效时间窗、勿扰/夜间/省电等策略。
3. 口袋模式或遮挡策略评估是否拦截通知亮屏。
4. 策略允许后，`PowerManagerService` 发起 waking up。
5. 显示电源模式切换，`onSetDisplayPowerMode` 或同类日志出现。
6. `DisplayPowerController` / `LocalDisplayAdapter` / backlight 写入体现实际亮屏。
7. 如果策略拒绝，应能在日志中找到拒绝原因，而不是进入亮屏链路后无动作。

如果当前日志只有通知到达但没有有效时间判断，不能确认策略允许；如果策略允许但没有 `Waking up`，应定位到策略触发到电源唤醒之间。

### 与飞书正常案例的对比方式

- 对比“通知到达 -> 策略有效 -> 口袋模式未拦截 -> Waking up -> display mode/backlight”是否完整。
- 正常案例中的时间窗和策略结果只能作为参考，当前结论要以当前配置和当前日志为准。
- 不要把正常案例中的唤醒打印当作当前问题已经发起唤醒的证据。

---

## 标准处理流程

### Step 1：确认是否收到通知事件（`check_notification_received`）

- **目标**：确认通知确实到达了系统侧的锁屏通知模块。
- **关键证据**：`TranLockScreenNotification.*onNotificationPosted`
- **判断分支**：
  - 若没有：属于“通知未到达/被过滤”，需要先从通知发布链路排查
  - 若有：进入 Step 2

### Step 2：检查有效时间与勿扰相关判断（`check_effective_time`）

- **目标**：确认是否因为有效时间窗/勿扰策略导致不亮屏。
- **关键证据**：
  - `TranLockScreenNotification.*isNotifyScreenOnEffectiveTime`
  - `TranLockScreenNotification.*totalNowMinutes`
- **判断分支**：
  - 若判断为无效：归因到策略限制（给出时间窗证据），并建议验证开关/配置
  - 若有效：进入 Step 3

### Step 3：检查是否被口袋模式拦截（`check_pocket_mode`）

- **目标**：确认 `NotificationWakePocketModeListener` 是否拦截了亮屏。
- **关键证据**：`TranPocketModeController.*NotificationWakePocketModeListener`
- **判断分支**：
  - 若拦截：需要解释口袋模式判定依据，并建议验证遮挡环境/传感器
  - 若未拦截：进入 Step 4

### Step 4：检查系统是否真正发起唤醒（`check_wakeup`）

- **目标**：确认系统从 Dozing/灭屏状态开始唤醒。
- **关键证据**：`PowerManagerService.*Waking up`
- **判断分支**：
  - 若无唤醒：说明策略虽允许，但未触发唤醒链路（需要继续追查触发条件）
  - 若有唤醒：进入 Step 5

### Step 5：检查显示电源模式切换与背光写入（`check_display_power`）

- **目标**：确认 display power mode 切换与 backlight 写入发生，亮屏闭环完成。
- **关键证据**：
  - `TranPowerStateChangedController.*onSetDisplayPowerMode`
  - `LocalDisplayAdapter.*backlight`
- **判断分支**：
  - 模式切换有但背光无：偏显示/背光写入链路
  - 背光有但仍黑屏：进一步补齐面板/合成相关证据

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| 通知未到达/被过滤 | Step 1 缺失 | 从通知发布/权限/渠道配置排查 |
| 有效时间/勿扰限制 | Step 2 判定无效 | 输出时间窗证据，建议调整配置验证 |
| 口袋模式误拦截 | Step 3 拦截 | 验证遮挡环境；排查 proximity/姿态传感器 |
| 唤醒链路未触发 | Step 4 缺失 | 继续追查触发条件与策略 |
| 显示模式/背光链路异常 | Step 5 异常 | 排查显示电源模式与 backlight 写入路径 |

---

## 常用回答动作

- 先要时间点与复现窗口（通知前后 1-2 分钟）
- 让用户确认是否有勿扰/夜间/省电配置
- 让用户说明复现时是否放在口袋或遮挡

---

## 失败时的降级策略

1. 将问题拆成“策略允许”与“唤醒执行”两段分别给出证据
2. 列出缺失证据与最小验证动作
3. 必要时接力到通知策略或传感器链路团队

---

## 证据约束

- 没有通知到达系统侧的证据时，不能判断亮屏策略异常。
- 没有有效时间/勿扰/策略判断时，不能确认系统允许通知亮屏。
- 没有 pocket mode 判断时，不能排除遮挡/口袋模式拦截。
- 没有 `Waking up` 时，不能确认电源唤醒已触发。
- 没有 display mode 或 backlight 证据时，不能把问题确定归因到显示/驱动写入。
- Markdown 和飞书正常案例只用于对比正常链路，不是当前问题事实。
