---
name: power-sensor-proximity-brightness
description: "电话场景遮挡Sensor亮度异常分析: 电话场景下接近传感器遮挡后灭屏或移开后亮屏过程中出现的异常分析 | 遮挡/proximity/sensor/接近/电话亮度/通话亮度/靠近灭屏/移开亮屏 | 当用户报告与「电话场景遮挡Sensor亮度异常分析」相关的日志分析需求时使用"
---

# 电话场景遮挡Sensor亮度异常分析

## 适用范围

- 通话靠近耳朵后应灭屏但 **不灭屏**
- 通话移开后应亮屏但 **不亮屏**
- 亮灭屏频繁抖动（疑似 proximity 防抖/阈值问题）
- 接近事件有，但 DisplayPowerController/LocalDisplayAdapter 未形成闭环

---

## 不适用场景

- 双击/通知/Power 键触发的亮屏：优先 `power-display-double-tap-wake` / `power-display-notification-wake` / `power-display-power-key-screen`
- 到时间自动灭屏：优先 `power-display-timeout-screen-off`
- 单纯亮度自动调节（非通话遮挡）：优先 `power-backlight-auto-anomaly`

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
- [ ] 检查 proximity 事件与防抖（`check_proximity_event`）
- [ ] 确认遮挡判定为 Positive 并启动灭屏（`check_proximity_positive`）
- [ ] 检查灭屏亮度动画与 reason（`check_screen_off_brightness`）
- [ ] 确认移开判定并启动亮屏（`check_proximity_negative`）
- [ ] 检查亮屏恢复与 reason 回切（`check_screen_on_recovery`）
- [ ] 检查适配层 backlight 写入证据（`check_backlight_write`）
```

---

## 分析前的最小证据集

- 是否在通话中（拨号/接通/免提/听筒/蓝牙）
- 复现方式：靠近遮挡多久、移开多久、是否快速来回
- 发生时间点（分钟级）与持续时间
- 是否使用贴膜/保护壳（可能影响 proximity）
- 是否可复现、DUT/REF 是否一致

---

## 快速判断（是否命中 proximity 链路）

典型信号：

- 接近事件处理：
  - `DisplayPowerProximityStateController.*handleProximitySensorEvent`
- 遮挡判定（Positive）：
  - `DisplayPowerProximityStateController.*Positive`
- 移开判定（Negative / Applying proximity）：
  - `DisplayPowerProximityStateController.*Applying proximity`
- 亮度动画与 reason：
  - `DisplayPowerController.*animateScreenBrightness`
  - `DisplayPowerController.*reason`
- 适配层与写入：
  - `LocalDisplayAdapter.*handleProximitySensorEvent`
  - `LocalDisplayAdapter.*backlight`

---

## 正常链路参考（用于和当前日志对比）

正常通话 proximity 亮灭屏链路应当能看到下面的阶段顺序。飞书里的正常打印案例只用于对比链路完整性，不能作为当前问题证据。

1. 通话进入听筒/非免提等需要 proximity 控制屏幕的状态。
2. 接近传感器事件上报到 `DisplayPowerProximityStateController`。
3. 遮挡时经过防抖后判定为 Positive，并应用 proximity 灭屏策略。
4. `DisplayPowerController` 将屏幕/亮度目标收敛到 off 或 target=0。
5. `LocalDisplayAdapter` / backlight 写入体现屏幕实际灭屏。
6. 移开后判定为 Negative，并解除 proximity 约束。
7. 亮度目标恢复到 manual/automatic 或通话前策略状态，backlight 写入同步恢复。

如果当前日志只看到传感器事件但没有 Positive/Negative 判定，只能定位到传感器上报到判定层之间；如果有判定但无动画/写入，只能定位到显示电源状态机或写入层附近。

### 与飞书正常案例的对比方式

- 对比“事件上报 -> 判定 Positive/Negative -> 亮灭屏动画 -> backlight 写入”是否完整。
- 正常案例中的防抖时长和阈值只能作为参考，具体判断要看当前项目配置和当前日志时间线。
- 不要因为正常案例有某条打印，就认定当前日志也发生了该阶段。

---

## 标准处理流程

### Step 1：检查 proximity 事件与防抖（`check_proximity_event`）

- **目标**：确认接近事件进入处理链路，并关注防抖延迟是否异常。
- **关键证据**：`DisplayPowerProximityStateController.*handleProximitySensorEvent`
- **判断分支**：
  - 若无事件：偏传感器上报/权限/注册问题（需要补齐传感器侧证据）
  - 若有事件：进入 Step 2

### Step 2：确认遮挡判定为 Positive 并启动灭屏（`check_proximity_positive`）

- **目标**：确认遮挡被判定为 Positive，灭屏链路应开始收敛。
- **关键证据**：`DisplayPowerProximityStateController.*Positive`
- **判断分支**：
  - 若遮挡却不 Positive：可能阈值/贴膜/环境干扰
  - 若 Positive：进入 Step 3

### Step 3：检查灭屏亮度动画与 reason（`check_screen_off_brightness`）

- **目标**：确认亮度动画 target=0.0，reason 切到 screen_off（或接近传感器相关 reason）。
- **关键证据**：
  - `DisplayPowerController.*animateScreenBrightness`
  - `DisplayPowerController.*reason`
- **判断分支**：
  - Positive 有但亮度不归零：偏显示电源状态机/策略阻塞
  - 归零正常：进入 Step 4（移开亮屏验证）

### Step 4：确认移开判定并启动亮屏（`check_proximity_negative`）

- **目标**：移开后判定为 Negative，亮屏链路应开始恢复。
- **关键证据**：`DisplayPowerProximityStateController.*Applying proximity`
- **判断分支**：
  - 移开却不 Negative：传感器/阈值/干扰可能性高
  - 判定正常：进入 Step 5

### Step 5：检查亮屏恢复与 reason 回切（`check_screen_on_recovery`）

- **目标**：确认亮度目标恢复，并且 reason 从 screen_off 回到 manual/automatic。
- **关键证据**：
  - `DisplayPowerController.*animateScreenBrightness`
  - `DisplayPowerController.*reason`

### Step 6：检查适配层 backlight 写入证据（`check_backlight_write`）

- **目标**：确认 LocalDisplayAdapter 的 backlight 写入与亮灭屏目标一致。
- **关键证据**：`LocalDisplayAdapter.*backlight`
- **判断分支**：
  - Framework 目标正常但写入异常：偏 HAL/驱动/映射
  - 写入正常但体验异常：需要补齐更多面板/合成证据

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| 传感器事件不上报 | Step 1 缺失 | 排查传感器注册/权限/硬件；补齐传感器日志 |
| 遮挡/移开判定错误 | Step 2/4 判定异常 | 排查阈值、贴膜/保护壳、环境干扰；建议对比无贴膜 |
| 状态机未驱动亮灭屏 | Step 3/5 无动画/reason 异常 | 排查 DisplayPowerController 分支与阻塞 |
| 写入链路异常 | Step 6 不一致 | 排查 LocalDisplayAdapter → lights HAL → 节点写入 |

---

## 常用回答动作

- 先要“接通通话后靠近/移开”的时间点
- 让用户说明是否贴膜/壳体遮挡 proximity
- 若抖动：建议连续做 3~5 次靠近/移开并记录每次时间点

---

## 失败时的降级策略

1. 明确卡在：传感器事件 / 判定结果 / 状态机动画 / 写入链路 哪一层
2. 列出缺失证据与最小验证动作
3. 必要时接力到传感器或 HAL/驱动链路

---

## 证据约束

- 没有通话状态证据时，不能确认应由 proximity 控制亮灭屏。
- 没有 sensor event 时，不能判断 DisplayPowerController 异常。
- 没有 Positive/Negative 判定时，不能确认遮挡/移开已被系统接受。
- 没有动画或 backlight 写入证据时，不能把问题确定归因到 HAL/驱动。
- Markdown 和飞书正常案例只用于对比正常链路，不是当前问题事实。
