---
name: power-backlight-hbm-enter
description: "HBM高亮模式进入/退出异常分析: 环境光超过/低于20000lux时进入/退出HBM高亮模式过程中出现的异常分析 | HBM/高亮/high brightness/20000lux/强光/户外亮度/阳光/最大亮度 | 当用户报告与「HBM高亮模式进入/退出异常分析」相关的日志分析需求时使用"
---

# HBM高亮模式进入/退出异常分析

## 适用范围

- 强光下屏幕仍不够亮（疑似 HBM 未进入）
- HBM 进入后无法退出（环境变暗仍保持高亮）
- 进入/退出动画异常（跳变、卡住、频繁进出）
- 明显满足强光条件但被策略拦截（温度/电量/省电/口袋模式等）

---

## 不适用场景

- 普通自动亮度调节异常（非 HBM 阈值附近）：优先 `power-backlight-auto-anomaly`
- 手动亮度拖动异常：优先 `power-backlight-manual-adjust`
- 相机/视频 override 亮度：优先 `power-backlight-camera-video`
- 接近/遮挡导致策略变化：优先 `power-sensor-proximity-brightness`

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
- [ ] 检查自动亮度是否到达最大值（`check_auto_brightness_max`）
- [ ] 检查 HBM 传感器状态与限制条件（`check_hbm_sensor_state`）
- [ ] 检查 HBM 进入动画（`check_hbm_enter_animation`）
- [ ] 检查 HBM 退出流程（`check_hbm_exit`）
- [ ] 检查背光写入与适配层证据（`check_backlight_write`）
```

---

## 公共亮度策略前置检查
在判定当前场景为异常前，必须先排查以下正常亮度策略是否正在生效：温控限亮、App 降亮度、常温最大亮度限制、户外增强、省电模式。
判断优先级：温控优先级最高；没有温控时，如果多个亮度策略同时存在，通常谁计算出的亮度最低就使用谁的亮度。户外增强属于增亮策略，但可能被温控、省电或最大亮度限制压住。
如果日志命中 `power-backlight-policy-factors` 中的策略证据，应在结论中单独说明：命中的策略、关键日志、该策略导致亮度上升/下降/限制上限，以及这是正常策略生效还是“该触发未触发 / 不该触发却触发”的策略异常。
---

## 分析前的最小证据集

- 环境：室外强光/手电筒照射/光照强度大致范围（是否接近 20000 lux ）
- 发生时间点（分钟级）与持续时间
- 自动亮度开关状态（开/关）
- 设备状态：温度是否高、低电量/省电模式、口袋模式/遮挡
- 是否可稳定复现、是否 DUT/REF 一致

---

## 快速判断（是否命中 HBM 链路）

典型信号：

- 自动亮度到达上限或接近上限：
  - `AutomaticBrightnessController.*updateAutoBrightness`
- HBM 条件评估：
  - `TranHBMController.*updateHbmLightSensorState`
- HBM 进入动画：
  - `TranHBMController[0].*animate Hbm Brightness`
- HBM 退出：
  - `TranHBMController[0].*exitHbmBrightness`
- 背光写入/适配层：
  - `LocalDisplayAdapter.*backlight`

---

## 正常链路参考（用于和当前日志对比）

正常 HBM 进入/退出链路应当能看到下面的阶段顺序。飞书里的正常打印案例可以帮助确认阶段顺序，但不能替代当前日志证据。

1. 环境光达到 HBM 触发区间，自动亮度先接近或达到普通最大亮度。
2. `TranHBMController` 或相关控制器评估 HBM 条件，包括 lux、温度、电量、省电、口袋/遮挡等限制。
3. 条件满足后，HBM 状态机进入高亮路径，并触发 HBM 亮度动画。
4. `LocalDisplayAdapter` / lights HAL / backlight 写入应从普通最大亮度过渡到 HBM 目标。
5. 环境光回落或限制条件出现后，应触发 `exitHbmBrightness` 或同类退出路径。
6. 退出动画和写入应回落到普通亮度范围，并稳定在非 HBM 状态。

如果当前日志只看到自动亮度拉满，但没有 HBM 条件评估，不能判断 HBM 状态机异常；应先补齐 HBM controller 相关日志。

### 与飞书正常案例的对比方式

- 对比“普通最大亮度 -> HBM 条件评估 -> HBM 进入动画 -> backlight 写入 -> 退出回落”是否完整。
- 当前日志缺少某个阶段时，只能定位到该阶段附近。
- 正常案例中的阈值和时序只能作为参考，具体阈值仍以当前项目配置和当前日志为准。

---

## 标准处理流程

### Step 1：检查自动亮度是否到达最大值（`check_auto_brightness_max`）

- **目标**：确认强光条件下自动亮度是否已拉到最大值（HBM 进入前提之一）。
- **关键证据**：`AutomaticBrightnessController.*updateAutoBrightness`
- **判断分支**：
  - 若未到达最大值：先回到自动亮度专题（lux/阈值/策略），HBM 不一定触发
  - 若到达最大值：进入 Step 2

### Step 2：检查 HBM 传感器状态与限制条件（`check_hbm_sensor_state`）

- **目标**：确认 HBM 条件是否满足（温度、电量、省电模式、口袋模式等）。
- **关键证据**：`TranHBMController.*updateHbmLightSensorState`
- **判断分支**：
  - 若被限制拦截：根因偏策略（温控/省电/口袋模式等），需要说明“为何不进入”
  - 若条件满足：进入 Step 3

### Step 3：检查 HBM 进入动画（`check_hbm_enter_animation`）

- **目标**：确认亮度从普通最大值（如 1.0）过渡到 HBM 目标（如 1.5）的动画链路。
- **关键证据**：`TranHBMController[0].*animate Hbm Brightness`
- **判断分支**：
  - 若进入动画缺失：可能是状态机未触发/被覆盖
  - 若进入动画存在但体验异常：结合 Step 5 验证写入一致性

### Step 4：检查 HBM 退出流程（`check_hbm_exit`）

- **目标**：环境光下降后能否触发退出并回落到普通亮度。
- **关键证据**：`TranHBMController[0].*exitHbmBrightness`
- **判断分支**：
  - 退出不触发：关注 lux 回落阈值/滞回/时间窗配置
  - 退出触发但不回落：关注动画/写入链路

### Step 5：检查背光写入与适配层证据（`check_backlight_write`）

- **目标**：确认 `LocalDisplayAdapter` 的 backlight 值是否与 HBM 目标一致，并能正确过渡。
- **关键证据**：`LocalDisplayAdapter.*backlight`
- **判断分支**：
  - 目标正确但写入异常：偏 HAL/驱动/映射
  - 写入正确但体验异常：考虑面板能力/可视效果/亮度曲线

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| 强光条件未满足/自动亮度未拉满 | Step 1 未到上限 | 回到自动亮度链路排查 lux/阈值/策略 |
| 条件被限制拦截（温度/省电/口袋） | Step 2 显示不满足 | 明确限制条件与策略依据；建议验证环境/状态 |
| 状态机触发但动画/写入异常 | Step 3/5 不一致 | 排查动画参数、LocalDisplayAdapter 写入与 HAL |
| 退出阈值/滞回异常导致不退出 | Step 4 不触发 | 检查回落阈值/滞回/时间窗配置与日志时间线 |

---

## 常用回答动作

- 让用户确认是否确实处于强光阈值附近（并提供时间点）
- 让用户提供温度/电量/省电模式/口袋模式状态
- 若进入/退出频繁：建议记录一段连续时间窗日志用于分析滞回/延迟

---

## 失败时的降级策略

1. 明确卡在：强光条件 / 限制条件 / 状态机触发 / 写入链路 哪一层
2. 列出缺失证据（时间窗、lux/状态日志、LocalDisplayAdapter 写入）
3. 给出最小验证动作（优先 1 个）

---

## 证据约束

- 没有强光/lux 或自动亮度拉满证据时，不能确认满足 HBM 前置条件。
- 没有 `TranHBMController` 条件评估时，不能判断是状态机拒绝还是日志缺失。
- 没有进入/退出动画证据时，不能确认 HBM 状态转换已经发生。
- 没有 backlight 写入证据时，不能把问题确定归因到 HAL/驱动。
- Markdown 和飞书正常案例只用于对比正常链路，不是当前问题事实。
