---
name: power-backlight-policy-factors
description: "亮度策略影响因素识别: 识别温控限亮、App降亮度、常温最大亮度限制、户外增强、省电模式等正常策略对亮度值的影响，避免把策略生效误判为背光异常 | 温控限亮/热控限亮/APP降亮度/App亮度/最大亮度限制/户外增强/省电限亮/亮度策略 | 当用户报告与「亮度策略影响因素识别」相关的日志分析需求时使用"
funcType: "AI故障分析"
category: "功耗"
---

# 亮度策略影响因素识别

## 核心判断原则

1. 亮度下降不一定是异常，可能是温控、省电、App 限亮、常温最大亮度限制等策略正常生效。
2. 温控优先级最高。如果温控已经命中，优先按照温控目标亮度解释当前亮度变化。
3. 没有温控时，如果多个亮度策略同时存在，通常取计算后亮度最低的策略结果作为最终亮度。
4. 只有在“该触发时没有触发”或“不该触发时触发了”时，才把这些策略本身作为异常方向。
5. 结论必须引用当前日志中的策略证据，不能只因为问题现象是“变暗/变亮”就推断某个策略生效。

## 温控限制亮度

关键日志：

- `thermalLightController: level1=LevelValue{trigger=41, exit=39, brightness=450}`
- `thermalLightController: Level-2 ..., temp=42.069, level=2, brightnessNits=350`
- `thermalLightController: updateBrightness!!!!!`
- `thermalLightController: Normal: targetNits=350 ,targetRatio=0.43521583 ,originNits=760.0 ,oriRatio=1.0`

正常解释：当日志中出现温控等级配置、当前温度、level 和 `targetNits` 时，说明热控正在根据温度限制最大亮度。例如原始亮度是 `760 nits`，温控后目标亮度变为 `350 nits`，这种亮度下降应优先解释为温控策略生效。

异常边界：

- 温度达到 trigger 阈值，但没有对应 level 或 targetNits。
- 温度已经低于 exit 阈值，但限亮长期不解除。
- level 与配置不匹配，例如温度只满足 level1 却按 level3 限制。

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

## 省电模式限亮

关键日志：

- `TranBatterySaveBrightnessLimitController ... onBatterySaveModeChange 1`
- `shouldBrightnessLimit ... BatterySaveBrightnessConfigInfo{id=1, switchData=1, nits=[70, 130], ratios=[0.0, 0.15], rateIns=[0, 15, 15], rateOuts=[0, 15, 15]}`
- `getBrightness newBrightness = 0.17372184 brightness = 0.20437862 brightnessnit = 135.80302`
- `onBatterySaveModeChange 0`
- `getBrightnessTime: outtime 15.0`

正常解释：省电模式打开后，系统会根据 nits 区间和 ratios 计算压低后的 `newBrightness`。省电关闭后，应进入退出限亮流程，并出现 `outtime`。

异常边界：

- 省电开启后没有限亮计算。
- 省电关闭后仍持续按省电模式压低亮度。
- `newBrightness` 高于原始亮度，或与 ratios 配置明显不符。

---

# 亮度策略影响因素识别
本 skill 是所有亮度类分析的公共前置检查。分析手动亮度、自动亮度、HBM、App 亮度、相机/视频 override 等问题时，必须先检查这些正常策略是否正在影响亮度值。

---

## App 降亮度

关键日志：

- `TranAppBrightnessChangeController ... [applyBrightnessLimitedByApp]`
- `[setTranAppBrightnessOptimizationComplete] = false`
- `[getTranAppBrightness] limitPercentage: 0.2 newBrightness: 0.18851571 brightness: 0.23564464 brightnessNits: 159.48883 timeIn: 15.0 timeOut: 15.0`
- `getTranAppBrightnessTime: outtime 15.0`
- `[setTranAppBrightnessOptimizationComplete] = true`

正常解释：进入某些 App 后，`TranAppBrightnessChangeController` 会计算新的亮度目标。如果 `newBrightness` 小于原始 `brightness`，并且有 `timeIn`，说明 App 降亮度策略正在生效。退出阶段应看到 `outtime`，最后完成标记恢复为 `true`。

异常边界：

- 进入目标 App 后应该限亮但没有 `applyBrightnessLimitedByApp` 或 `getTranAppBrightness`。
- 退出 App 后没有 `outtime`，或 `setTranAppBrightnessOptimizationComplete` 长期不回到 `true`。
- `limitPercentage` 或 `newBrightness` 与配置明显不符。

---

## 常温最大亮度限制

关键日志：

- `TranMaxBrightnessLimitController: getTranMaxBrightness newBrightness = 0.70292085 mCurrentLimitConfig.maxNit = 450 brightness = 0.8543307 brightnessnit = 570.8531`

正常解释：当光感低于项目设定阈值，例如低于 `2000 lux`，系统可能触发常温最大亮度限制。日志中 `maxNit = 450`，原始亮度对应 `570.8531 nits`，限制后 `newBrightness = 0.70292085`，说明亮度被限制在常温最大亮度范围内。

异常边界：

- 光感或场景已经满足更高亮度条件，但仍被常温最大亮度限制压住。
- `maxNit` 与项目配置不一致。
- 限制后亮度没有按 `newBrightness` 下发或恢复。

---

## 户外增强

关键日志：

- `TranOutdoorBrightnessController ... [onChange] mIsOutdoorSwitcte = true, mIsOutdoorBrightnessSwitcte = true, oldSwitch = false`
- `getOutdoorBrightness: newBrightness = 0.2862624 brightness = 0.20437862 percentage = 0.40064737`
- `getOutdoorBrightnessTime: time = 0.05`
- `mIsOutdoorSwitcte = false`

正常解释：户外增强打开时，`newBrightness` 通常高于原始 `brightness`，并伴随 `percentage` 和过渡时间。关闭时应看到 `mIsOutdoorSwitcte = false` 以及退出或切换时间。

异常边界：

- 户外开关打开但没有增亮计算。
- 户外开关关闭后仍持续按户外增强亮度计算。
- `newBrightness` 方向与户外增强预期相反。

---

## 省电模式限亮

关键日志：

- `TranBatterySaveBrightnessLimitController ... onBatterySaveModeChange 1`
- `shouldBrightnessLimit ... BatterySaveBrightnessConfigInfo{id=1, switchData=1, nits=[70, 130], ratios=[0.0, 0.15], rateIns=[0, 15, 15], rateOuts=[0, 15, 15]}`
- `getBrightness newBrightness = 0.17372184 brightness = 0.20437862 brightnessnit = 135.80302`
- `onBatterySaveModeChange 0`
- `getBrightnessTime: outtime 15.0`

正常解释：省电模式打开后，系统会根据 nits 区间和 ratios 计算压低后的 `newBrightness`。省电关闭后，应进入退出限亮流程，并出现 `outtime`。

异常边界：

- 省电开启后没有限亮计算。
- 省电关闭后仍持续按省电模式压低亮度。
- `newBrightness` 高于原始亮度，或与 ratios 配置明显不符。

---

## 多策略叠加

关键日志：

- `TranBrightnessController ... getTranBrightnessOptimizationBrightness reasons: [TranBatterySaveBrightnessLimitController, TranAppBrightnessChangeController]`

判断规则：

1. 如果温控命中，先按温控目标亮度判断。
2. 如果没有温控，但 App 限亮、省电、常温最大亮度、户外增强等策略同时出现，比较各自 `newBrightness` 或目标 nits。
3. 对于限制类策略，通常最终选择更低的亮度。
4. 户外增强是增亮策略，但仍可能被温控、省电、常温最大亮度等限制类策略压住。

---

## 分析输出要求

当识别到上述策略时，输出中应单独说明：

- 命中的亮度策略名称。
- 当前日志中的关键证据。
- 该策略导致亮度上升、下降或限制上限。
- 是否属于正常策略生效。
- 是否存在异常边界：该触发未触发，或不该触发却触发。
