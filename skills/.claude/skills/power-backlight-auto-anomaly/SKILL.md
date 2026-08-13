---
name: power-backlight-auto-anomaly
description: "自动背光异常分析: 自动亮度调节过程中出现的亮度计算、环境光采样、动画过渡等异常分析 | 自动亮度/自动背光/auto brightness/光感/环境光/lux/亮度跳变/亮度不变 | 当用户报告与「自动背光异常分析」相关的日志分析需求时使用"
funcType: "AI故障分析"
category: "功耗"
---

# 自动背光异常分析

## 适用范围

用于指导以下自动亮度链路问题的首轮分析与归因：

- 自动亮度 **不变**（环境明显变亮/变暗但亮度不调节）
- 自动亮度 **跳变/闪烁**（频繁大幅度变化，体验异常）
- 自动亮度 **变化方向错误**（变亮却变暗，或反之）
- 自动亮度 **延迟过大**（长时间不响应环境变化）
- 系统侧目标亮度正常，但 **HAL/背光节点写入异常**

---

## 不适用场景

- 明确为 **手动拖动亮度条** 引起：优先 `power-backlight-manual-adjust`
- 仅在 **相机/视频** 内发生（override/专属策略）：优先 `power-backlight-camera-video`
- 明确为 **HBM 高亮模式进入/退出**（强光>阈值）：优先 `power-backlight-hbm-enter`
- 明确为 **接近/遮挡/口袋模式** 影响：优先 `power-sensor-proximity-brightness`

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
- [ ] 检查环境光采样是否正常（`check_ambient_lux`）
- [ ] 检查自动亮度计算结果（`check_auto_brightness_calc`）
- [ ] 检查亮度动画与动画参数（`check_brightness_animation`）
- [ ] 确认最终亮度事件与 reason（`check_brightness_event`）
- [ ] 检查背光写入是否一致（`check_backlight_write`）
```

---

## 公共亮度策略前置检查
在判定当前场景为异常前，必须先排查以下正常亮度策略是否正在生效：温控限亮、App 降亮度、常温最大亮度限制、户外增强、省电模式。
判断优先级：温控优先级最高；没有温控时，如果多个亮度策略同时存在，通常谁计算出的亮度最低就使用谁的亮度。户外增强属于增亮策略，但可能被温控、省电或最大亮度限制压住。
如果日志命中 `power-backlight-policy-factors` 中的策略证据，应在结论中单独说明：命中的策略、关键日志、该策略导致亮度上升/下降/限制上限，以及这是正常策略生效还是“该触发未触发 / 不该触发却触发”的策略异常。
---

## 分析前的最小证据集

- 自动亮度开关状态（开/关）
- 环境变化方式：从室内到户外/用手遮挡光感/强光照射等
- 发生时间点（分钟级）与持续时间
- 是否在 doze/AOD/锁屏状态（自动亮度策略可能不同）
- 是否可稳定复现、是否 DUT/REF 一致
- 平台/版本/机型

### 推荐优先查看的日志

- `mainlogcat-log*` / `main_log*`：`AutomaticBrightnessController`、`DisplayPowerController` 关键日志
- `sys_log*` / `systemlogcat-log*`：显示电源策略、动画参数、HAL 调用链线索

---

## 快速判断（是否命中自动亮度链路）

出现以下任意一组信号通常可认为命中：

- 环境光采样/计算：
  - `AutomaticBrightnessController.*updateAmbientLux`
  - `AutomaticBrightnessController.*calculateAmbientLux`
- 自动亮度计算：
  - `AutomaticBrightnessController.*updateAutoBrightness`
- 亮度动画与动画参数：
  - `DisplayPowerController[0].*animateScreenBrightness`
  - `DisplayPowerController[0].*putScreenBrightnessAnimationSetting`
- 背光写入证据（不同平台不同）：
  - `android.hardware.lights-service.mediatek.*/sys/class/leds/lcd-backlight/brightness`
  - `LIGHTS.*/sys/class/backlight/sprd_backlight/brightness`

---

## 正常链路参考（用于和当前日志对比）

正常自动亮度链路应当能看到下面的阶段顺序。飞书里的正常打印案例可以作为这些阶段的参考，但不能当作当前问题证据。

1. ALS/环境光数据进入系统，`updateAmbientLux` 或 `calculateAmbientLux` 体现 lux 更新。
2. `AutomaticBrightnessController` 根据 lux、阈值、防抖和当前模式计算目标亮度。
3. `updateAutoBrightness` 输出新旧亮度变化，且变化方向与环境变化一致。
4. `DisplayPowerController` 接收到自动亮度目标，并进入 `animateScreenBrightness` 或相关动画/收敛流程。
5. `BrightnessEvent` 的 reason 应能解释为 automatic 或自动亮度链路相关原因。
6. lights HAL / backlight 节点写入值与 Framework 目标方向一致。
7. 最终亮度稳定，不应被 manual、override、HBM、doze/AOD 或省电策略意外覆盖。

如果当前日志缺少某一阶段，只能说链路断在该阶段附近；不要直接补全后续阶段。

### 与飞书正常案例的对比方式

- 可以说：“正常案例中 A 后通常出现 B，但当前日志没有 B，因此怀疑断在 A 到 B 之间。”
- 不要说：“飞书案例里出现了 B，所以当前问题也发生了 B。”
- 如果当前日志和正常案例完全一致，但用户仍感知异常，应优先考虑日志时间窗口不对、面板/曲线/感知差异或缺少底层写入证据。

---

## 标准处理流程

### Step 1：检查环境光采样是否正常（`check_ambient_lux`）

- **目标**：确认 ALS 采样与环形缓冲区更新正常，阈值与防抖逻辑是否符合预期。
- **关键证据**：`AutomaticBrightnessController.*updateAmbientLux`
- **判断分支**：
  - 若 lux 数据不更新/异常抖动：优先怀疑传感器/采样率/滤波配置问题
  - 若 lux 更新正常：进入 Step 2

### Step 2：检查自动亮度计算结果（`check_auto_brightness_calc`）

- **目标**：确认 `updateAutoBrightness` 产生了合理的目标亮度（新旧值变化、阈值判断）。
- **关键证据**：`AutomaticBrightnessController.*updateAutoBrightness`
- **判断分支**：
  - lux 正常但亮度不变：关注阈值/防抖/模式限制（doze/AOD/省电/户外优化）
  - 亮度计算有变化：进入 Step 3

### Step 3：检查亮度动画与动画参数（`check_brightness_animation`）

- **目标**：确认目标值、rate、曲线域参数设置合理，动画是否被中断/覆盖。
- **关键证据**：
  - `DisplayPowerController[0].*animateScreenBrightness`
  - `DisplayPowerController[0].*putScreenBrightnessAnimationSetting`
- **判断分支**：
  - 目标变化但动画频繁被打断：可能被其他 reason 覆盖（override/manual/临时亮度）
  - 动画正常：进入 Step 4

### Step 4：确认最终亮度事件与 reason（`check_brightness_event`）

- **目标**：确认最终亮度与 reason 为 automatic（避免误判为手动/override）。
- **关键证据**：`DisplayPowerController[0].*BrightnessEvent`
- **判断分支**：
  - reason 非 automatic：转去对应专题（manual/override/hbm 等）
  - reason 为 automatic：进入 Step 5

### Step 5：检查背光写入是否一致（`check_backlight_write`）

- **目标**：把问题落到“Framework 目标”还是“HAL/驱动实际写入”。
- **关键证据**：背光节点写入日志（本文 match_patterns 已覆盖常见路径）
- **判断分支**：
  - 目标正常但写入不一致：偏 HAL/驱动/节点映射
  - 写入一致但体验异常：考虑亮度曲线、面板特性、感知问题（需更进一步数据）

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| ALS lux 不更新/抖动 | Step 1 异常 | 检查传感器采样、滤波、防抖配置；补齐传感器相关日志 |
| lux 正常但亮度不变 | Step 2 无变化 | 排查阈值/模式限制（doze/AOD/省电/户外优化） |
| 目标变化但动画被覆盖 | Step 3 中断频繁 | 检查 reason 是否被 manual/override/hbm 覆盖 |
| 目标正确但写入异常 | Step 5 不一致 | 排查 lights HAL、背光节点路径与权限 |

---

## 常用回答动作

- 信息不足：先索取自动亮度开关状态、环境变化方式、发生时间点
- 怀疑被覆盖：让用户确认是否在相机/视频/通话遮挡/强光 HBM 场景
- 缺少写入证据：提示补齐系统 log，并扩大关键词 backlight/brightness/lights

---

## 失败时的降级策略

1. 明确当前只能定位到哪一层（ALS 采样 / 亮度计算 / 动画 / 写入）
2. 列出缺失证据（哪类日志/哪个时间窗口）
3. 给出最小验证动作（优先 1 个）
4. 必要时接力到 HAL/驱动或传感器链路团队

---

## 证据约束

- 自动亮度根因必须能回到当前日志中的 lux、目标亮度、动画或写入证据。
- 如果没有 `updateAmbientLux`，不能确认 ALS 采样正常。
- 如果没有 `updateAutoBrightness`，不能确认 Framework 已产生自动亮度目标。
- 如果没有背光写入证据，不能把问题确定归因到 HAL/驱动。
- Markdown 和飞书正常案例只提供分析方法与对照链路，不是当前问题事实。
