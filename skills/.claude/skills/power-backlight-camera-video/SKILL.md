---
name: power-backlight-camera-video
description: "相机/视频界面切换亮度异常分析: 打开相机或视频应用时亮度override切换以及退出时亮度恢复过程中出现的异常分析 | 相机/camera/视频/video/override/亮度覆盖/切换亮度/进入相机 | 当用户报告与「相机/视频界面切换亮度异常分析」相关的日志分析需求时使用"
---

# 相机/视频界面切换亮度异常分析

## 适用范围

- 打开相机/视频 App 时亮度 **突然变暗/变亮/闪烁**
- 相机内亮度被 override 后 **退出不恢复**
- override reason 出现但背光写入不一致（看起来没变化或变化过头）

---

## 不适用场景

- 常规 App（非相机/视频）切换亮度优化：优先 `power-backlight-app-optimization`
- 环境变化导致的自动亮度异常：优先 `power-backlight-auto-anomaly`
- 手动拖动亮度条异常：优先 `power-backlight-manual-adjust`

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
- [ ] 确认 App 切换事件与入口（`check_app_switch`）
- [ ] 确认 override reason 是否正确（`check_override_brightness`）
- [ ] 检查退出后是否恢复（`check_exit_restore`）
- [ ] 检查背光写入是否与目标一致（`check_backlight_write`）
```

---

## 公共亮度策略前置检查
在判定当前场景为异常前，必须先排查以下正常亮度策略是否正在生效：温控限亮、App 降亮度、常温最大亮度限制、户外增强、省电模式。
判断优先级：温控优先级最高；没有温控时，如果多个亮度策略同时存在，通常谁计算出的亮度最低就使用谁的亮度。户外增强属于增亮策略，但可能被温控、省电或最大亮度限制压住。
如果日志命中 `power-backlight-policy-factors` 中的策略证据，应在结论中单独说明：命中的策略、关键日志、该策略导致亮度上升/下降/限制上限，以及这是正常策略生效还是“该触发未触发 / 不该触发却触发”的策略异常。
---

## 分析前的最小证据集

- 从哪个 App 切到相机/视频（前台切换路径）
- 相机/视频 App 包名（是否 `com.transsion.camera/...` 等）
- 发生时间点（分钟级）与复现步骤（进入/退出/来回切）
- 自动亮度开关状态（开/关）

---

## 快速判断（是否命中 override 链路）

典型信号：

- App 切换：
  - `TranAppm/Monitor.*App switch`
- override reason：
  - `DisplayPowerController[0].*override`
- 亮度动画与动画参数：
  - `DisplayPowerController[0].*animateScreenBrightness`
  - `DisplayPowerController[0].*putScreenBrightnessAnimationSetting`
- 亮度事件（用于判断退出恢复）：
  - `DisplayPowerController[0].*BrightnessEvent`
- 背光写入：
  - `android.hardware.lights-service.mediatek.*/sys/class/leds/lcd-backlight/brightness`
  - `LIGHTS.*/sys/class/backlight/sprd_backlight/brightness`

---

## 正常链路参考（用于和当前日志对比）

正常相机/视频亮度 override 链路应当能看到下面的阶段顺序。飞书里的正常打印案例只用于对比链路完整性，不能作为当前问题证据。

1. 前台应用发生切换，日志能看到从普通 App 切入相机/视频 App。
2. 亮度策略识别到相机/视频包名或场景，进入 override 策略。
3. `DisplayPowerController` 的 reason 或 BrightnessEvent 能体现 override。
4. 目标亮度通过 `animateScreenBrightness` 或相关动画参数收敛。
5. HAL / backlight 写入与 override 目标方向一致。
6. 退出相机/视频后，reason 应从 override 回到 manual/automatic 或进入原先策略。
7. 恢复阶段的 backlight 写入应同步回落或回到进入前策略值。

如果当前日志只有 App switch，没有 override reason，不能判断写入链路异常；如果有 override 但没有退出恢复日志，只能判断进入阶段，不能确认退出不恢复。

### 与飞书正常案例的对比方式

- 对比“App switch -> override reason -> 亮度动画 -> backlight 写入 -> 退出恢复”是否完整。
- 正常案例中的包名和策略值只能作为参考，当前结论要基于当前日志里的包名、reason 和写入。
- 不要把正常案例中的退出恢复打印当作当前问题已恢复的证据。

---

## 标准处理流程

### Step 1：确认 App 切换事件与入口（`check_app_switch`）

- **目标**：确认“从哪个应用切到相机/视频”，建立时间线锚点。
- **关键证据**：`TranAppm/Monitor.*App switch`
- **判断分支**：
  - 缺失：优先扩大时间窗/补齐 main log
  - 存在：进入 Step 2

### Step 2：确认 override reason 是否正确（`check_override_brightness`）

- **目标**：确认亮度 reason 变为 override，并能关联到相机/视频包名。
- **关键证据**：`DisplayPowerController[0].*override`
- **判断分支**：
  - reason 未变为 override：可能策略未触发或被其他策略覆盖
  - reason 为 override：进入 Step 3/4 验证恢复与写入

### Step 3：检查退出后是否恢复（`check_exit_restore`）

- **目标**：确认退出相机/视频后 reason 从 override 恢复到 manual/automatic。
- **关键证据**：`DisplayPowerController[0].*BrightnessEvent`
- **判断分支**：
  - 不恢复：偏状态机回收/退出事件未识别
  - 恢复：进入 Step 4

### Step 4：检查背光写入是否与目标一致（`check_backlight_write`）

- **目标**：确认 override/恢复期间背光写入值与目标一致，避免“看起来没变/变过头”。
- **关键证据**：背光节点写入日志（本文 match_patterns 已覆盖常见路径）
- **判断分支**：
  - 目标变化但写入缺失/异常：偏 HAL/驱动/映射
  - 写入一致但体验异常：考虑亮度曲线、面板特性、感知问题（需补齐更多证据）

---

## 常见根因地图（示例）

| 根因方向 | 典型证据 | 建议动作 |
|---|---|---|
| App switch 缺失导致无法定位入口 | Step 1 缺失 | 扩大时间窗，确认日志来源与关键词 |
| override 未触发或被覆盖 | Step 2 不出现 override | 排查策略触发条件与其他 reason 覆盖 |
| 退出不恢复 | Step 3 override 不回收 | 追查退出事件与恢复触发点，补齐时间线 |
| 写入链路异常 | Step 4 不一致 | 排查 lights HAL/背光节点路径与权限 |

---

## 常用回答动作

- 先要“切换前后 App 包名”和时间点
- 若只在相机异常：优先怀疑 override 策略或包名匹配
- 若退出不恢复：建议复现时多次进入/退出并记录每次时间点

---

## 失败时的降级策略

1. 降级到“断点定位”：App switch → override reason → 退出恢复 → 写入一致性
2. 列出缺失证据与最小验证动作
3. 必要时接力到策略维护/显示写入链路方向

---

## 证据约束

- 没有 App switch 证据时，不能确认亮度变化由相机/视频切换触发。
- 没有 override reason 时，不能判断相机/视频 override 策略已生效。
- 没有退出后的 BrightnessEvent 或 reason 回切时，不能确认退出恢复异常。
- 没有 backlight 写入证据时，不能把问题确定归因到 HAL/驱动。
- Markdown 和飞书正常案例只用于对比正常链路，不是当前问题事实。
