---
name: power-backlight-app-optimization
description: "常规App界面切换亮度异常分析: 打开非相机/视频的常规应用时TranAppBrightnessChangeController优化亮度过程中出现的异常分析 | 应用亮度/app亮度/界面切换/app切换/亮度优化/前台切换/应用切换亮度/打开应用 | 当用户报告与「常规App界面切换亮度异常分析」相关的日志分析需求时使用"
---

# 常规App界面切换亮度异常分析

## 适用范围

- 切到某个常规 App（非相机/视频）时亮度 **被限制/被拉低** 且不符合预期
- 切 App 时亮度频繁变化（疑似优化策略重复触发）
- 退出该 App 后亮度 **不恢复**
- 优化过程不闭环（标记未完成）

---

## 不适用场景

- 相机/视频 App 的 override 亮度：优先 `power-backlight-camera-video`
- 明确为手动拖动亮度条：优先 `power-backlight-manual-adjust`
- 明确为自动亮度随环境变化：优先 `power-backlight-auto-anomaly`

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
| App switch 事件缺失导致无法关联 | Step 1 缺失 | 扩大时间窗，确认日志来源与关键词 |
| 限制参数异常 | Step 2 参数不合理 | 排查策略配置、包名匹配、阈值计算 |
| 优化标记不完成 | Step 3 未完成 | 排查状态机分支与异常退出路径 |
| 退出不恢复 | Step 4 不回收 | 追查退出事件与恢复触发点，补齐时间线 |

---

---

## 公共亮度策略前置检查
在判定当前场景为异常前，必须先排查以下正常亮度策略是否正在生效：温控限亮、App 降亮度、常温最大亮度限制、户外增强、省电模式。
判断优先级：温控优先级最高；没有温控时，如果多个亮度策略同时存在，通常谁计算出的亮度最低就使用谁的亮度。户外增强属于增亮策略，但可能被温控、省电或最大亮度限制压住。
如果日志命中 `power-backlight-policy-factors` 中的策略证据，应在结论中单独说明：命中的策略、关键日志、该策略导致亮度上升/下降/限制上限，以及这是正常策略生效还是“该触发未触发 / 不该触发却触发”的策略异常。
---

## 分析前的最小证据集

- 具体 App 包名/版本（从哪个 App 切到哪个 App）
- 发生时间点（分钟级）与复现步骤（切换频率/停留时长）
- 自动亮度开关状态（开/关）
- 是否在省电/特殊显示模式（可能影响策略）

---

## 快速判断（是否命中 App 亮度优化链路）

典型信号：

- App 切换事件：
  - `TranAppm/Monitor.*App switch`
- 优化控制器关键路径：
  - `TranAppBrightnessChangeController.*handleMessage`
  - `TranAppBrightnessChangeController.*getTranAppBrightness`
  - `TranAppBrightnessChangeController.*applyBrightnessLimitedByApp`
  - `TranAppBrightnessChangeController.*setTranAppBrightnessOptimizationComplete`
- DPC 侧优化标识/动画：
  - `DisplayPowerController[0].*TranAppBrightnessOptimization`
  - `DisplayPowerController[0].*animateScreenBrightness`

---

## 标准处理流程

### Step 1：确认前台切换事件与时序（`check_app_switch`）

- **目标**：确认“从哪个应用切到哪个应用”，并建立时间线锚点。
- **关键证据**：`TranAppm/Monitor.*App switch`
- **判断分支**：
  - 若缺失：可能日志不全/关键字不足，需要扩大时间窗或补齐 main log
  - 若存在：进入 Step 2

### Step 2：检查亮度限制参数是否合理（`check_brightness_limit`）

- **目标**：拿到 `limitPercentage / newBrightness` 等参数，判断是否配置/计算异常。
- **关键证据**：
  - `TranAppBrightnessChangeController.*getTranAppBrightness`
  - `TranAppBrightnessChangeController.*applyBrightnessLimitedByApp`
- **判断分支**：
  - 参数异常（比例过低/目标过暗）：偏策略/配置或计算问题
  - 参数正常但体验异常：结合 DPC 动画与写入证据进一步确认

### Step 3：检查优化过程是否完成闭环（`check_optimization_complete`）

- **目标**：确认最终 `setTranAppBrightnessOptimizationComplete` 设为 true，避免“半途而废”。
- **关键证据**：`TranAppBrightnessChangeController.*setTranAppBrightnessOptimizationComplete`
- **判断分支**：
  - 未完成：高概率导致反复触发/退出不恢复
  - 已完成：进入 Step 4

### Step 4：检查退出应用后亮度是否恢复（`check_brightness_restore`）

- **目标**：确认优化标记/状态在退出后回收，亮度回到原策略（manual/automatic）。
- **关键证据**：`DisplayPowerController[0].*TranAppBrightnessOptimization`
- **判断分支**：
  - 不恢复：需要找“退出事件”与“恢复动作”是否触发，可能缺少切换日志或状态机未走到

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| App switch 事件缺失导致无法关联 | Step 1 缺失 | 扩大时间窗，确认日志来源与关键词 |
| 限制参数异常 | Step 2 参数不合理 | 排查策略配置、包名匹配、阈值计算 |
| 优化标记不完成 | Step 3 未完成 | 排查状态机分支与异常退出路径 |
| 退出不恢复 | Step 4 不回收 | 追查退出事件与恢复触发点，补齐时间线 |

---

## 常用回答动作

- 先要“切换前后 App 包名”和时间点
- 建议复现时录一段连续切换日志（覆盖多次切换）
- 若仅某个 App 异常：优先怀疑包名匹配/白名单/策略配置

---

## 失败时的降级策略

1. 降级到“策略断点定位”：App switch → 限制参数计算 → 完成标记 → 退出回收
2. 列出缺失证据（包名/时间窗/关键日志）
3. 给出最小验证动作（优先 1 个）
