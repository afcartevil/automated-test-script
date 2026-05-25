# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词：

```text
kernel_log: touch|fts|cts|gtp|nvt|chsc|ilitek|tcm
main_log/sys_log: KeyguardGesture|keycode
```

## 关键日志示例与解读

### TP 驱动加载

**日志示例**：

```text
// 判断启动模式，只有模式0(normal_boot),TP 才会加载
modprobe: [tran_touch-INFO]tran_tp_get_boot_mode 199:bootmode is 0
modprobe: [tran_touch-INFO]flod_main_device_init 942:bootmode 0 load touch !

//LCD屏opsMediator需要注册以支持TP手势功能、oled屏无需注册
modprobe: [tran_touch-INFO]ext_tp_function 195:opsMediator not support

//检查匹配的TP IC型号
kworker/u32:2: [tran_touch-INFO]check_support_ic 315:controller[0],support_ic: ft3682g

//加载供应商TP IC驱动成功，TP IC不唯一，视具体项目而定
kworker/u32:2: [tran_touch-INFO]match_tp_controller 441:load main controller vendor:focaltech ic:ft3682g success !!!
```

**解读**：

- `bootmode is 0` 表示 normal boot，TP 具备加载前提。
- `support_ic` / `load main controller ... success` 表示 TP IC 匹配并完成主驱动加载。
- `opsMediator not support` 仅说明 LCD 屏场景的手势依赖项，OLED 屏无需据此直接判异常。

### 驱动正常工作

**日志示例**：

```text
//手指触摸屏幕
irq/26-mtk-tpd: [FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (1009, 1932) touch up!
//手指离开屏幕
irq/26-mtk-tpd: [FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (892, 1518) touch down!
```

**解读**：

- 存在 `touch up` / `touch down` 说明亮屏常规触摸链路是工作的。
- 可作为“驱动正常工作、问题收敛到灭屏手势链路”的基础证据。

### 亮屏 TP 工作流

**日志示例**：

```text
//开始亮屏，唤醒TP
binder:1192_3: [tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start

//TP从灭屏手势模式切换为亮屏模式
kworker/u32:5: [tran_touch-INFO]state_change_machine 169:[main]: TRAN_GESTURE_SUSPEND_MODE --> TRAN_ACTIVE_MODE

//亮屏唤醒TP结束
kworker/u32:5: [tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
```

**解读**：

- 关键是看到 `TRAN_GESTURE_SUSPEND_MODE --> TRAN_ACTIVE_MODE`。
- 说明 TP 从灭屏手势模式恢复到亮屏正常工作模式。

### 灭屏 TP 工作流

**日志示例**：

```text
//开始灭屏，切换TP模式
binder:1192_3: [tran_touch-INFO]nvt_disp_notifier_callback 119:[main]: drm notify tp suspends start

//TP从亮屏模式切换为灭屏手势模式
 binder:1192_3: [tran_touch-INFO]state_change_machine 169:[main]: TRAN_ACTIVE_MODE --> TRAN_GESTURE_SUSPEND_MODE

//灭屏通知TP结束
binder:1192_3: [tran_touch-INFO]nvt_disp_notifier_callback 128:[main]: drm notify tp suspends end
```

**解读**：

- 关键是看到 `TRAN_ACTIVE_MODE --> TRAN_GESTURE_SUSPEND_MODE`。
- 若灭屏进入的是普通 `TRAN_SUSPEND_MODE`，通常说明系统或驱动未开启手势功能。

### TP 驱动开启手势功能

**日志示例**：

```text
//开启TP双击亮屏手势
[tran_touch-INFO]gesture_data_write 289:gesture_data_write code1[cc] enable[1]

//开启音乐手势
[tran_touch-INFO]gesture_data_write 289:gesture_data_write code1[aa] enable[1]
[tran_touch-INFO]gesture_data_write 289:gesture_data_write code1[bb] enable[1]
[tran_touch-INFO]gesture_data_write 289:gesture_data_write code1[ab] enable[1]
[tran_touch-INFO]gesture_data_write 289:gesture_data_write code1[ba] enable[1]

//开启快速启动手势
[tran_touch-INFO]gesture_data_write 289:gesture_data_write code1[ff] enable[1]

//未支持该手势
[tran_touch-INFO]GestureHandle 430:[GESTURE]Sorry, this gesture has been disabled.
```

**解读**：

- `gesture_data_write ... enable[1]` 说明对应手势已被系统下发使能。
- `Sorry, this gesture has been disabled.` 说明当前手势未支持或被禁用。

### TP 驱动手势上报

**日志示例**：

```text
//驱动上报手势成功
irq/26-mtk-tpd: [tran_touch-INFO]GestureHandle 454:[GESTURE]gesture report KEY_F26 done !
```

**解读**：

- `gesture report KEY_F26 done !` 是 TP 侧已完成手势上报的直接证据。
- 到这一步若用户问题仍存在，后续重点转到 `main_log` / `sys_log`。

### Framework 处理手势

**日志示例**：

```text
//上层收到驱动上报的手势
WindowManager: interceptKeyBeforeQueueing keyCode = 355, down = true, policyFlags = 33554432, isWakeKey = false, isKeyGestureTriggered = false
WindowManager: interceptKeyBeforeQueueing keyCode = 355, down = false, policyFlags = 33554432, isWakeKey = false, isKeyGestureTriggered = false

//亮屏灭屏TP手势处理
KeyguardGestureService: onStartCommand method=onFinishedWakingUp

//TP 音乐手势、快速启动手势处理
KeyguardGestureService: onStartCommand method=dispatchTPGesture
```

**解读**：

- `keyCode = 355` 说明 framework 已收到对应 TP 手势键值。
- `onFinishedWakingUp` 关联亮屏 / 灭屏类手势处理。
- `dispatchTPGesture` 关联音乐手势、快速启动等功能处理。

### 双击亮屏口袋模式判断

**日志示例**：

```text
//此时未处于口袋模式，双击可以亮屏
TranDoubleTapGesture: doubleTapWakePocketModeListener onPocketModeChanged: false
//此时处于口袋模式，双击不亮屏
TranDoubleTapGesture: doubleTapWakePocketModeListener onPocketModeChanged: true
```

**解读**：

- `onPocketModeChanged: true` 时，双击亮屏会被口袋模式拦截。
- 双击不亮屏问题必须结合距离传感器校准结论一起判断。

## 扩展参考

### TP 手势键值对应与功能介绍

| 操作类型 | 操作码 | Framework keycode |
|---|---|---|
| 双击 | `0xcc` | `355` |
| 上滑 | `0xba` | `355` |
| 下滑 | `0xab` | `355` |
| 左滑 | `0xbb` | `355` |
| `c` | `0x63` | `355` |
| `m` | `0x6d` | `355` |
| `w` | `0x77` | `355` |
| `v` | `0x76` | `355` |
| `z` | `0x7a` | `355` |
| `o` | `0x6f` | `355` |
| `e` | `0x65` | `355` |
| `s` | `0x73` | `355` |
| 单击 | `0xbe` | `333` |
| 指纹 | `0xbe` | `356` |

其中 `c`、`m` 等操作表示灭屏时在屏幕上划对应字母。

### input_report_key 上报键值

```text
单击：                      KEY_F20     190
指纹事件：                  KEY_FINGER  195
其他（双击、音乐、字符）:    KEY_F26      198
```
