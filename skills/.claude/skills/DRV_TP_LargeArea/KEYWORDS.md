# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词（竖线分隔，可直接用于grep）：

**kernel_log 关键词：**

```
touch|fts|cts|gtp|nvt|chsc|ilitek|tcm|large area
```

> 备注：`large area` 用于直接命中驱动上报大面积键值的日志行（如 `Large area touch down`），可在排查根因B（驱动是否上报大面积键值）时快速定位。

**main_log / sys_log 关键词：**

```
KeyguardGesture|keycode
```

## 关键日志示例与解读

### 1. TP驱动加载

**日志示例**：

```
// 判断启动模式，只有模式0(normal_boot),TP 才会加载
modprobe: [tran_touch-INFO]tran_tp_get_boot_mode 199:bootmode is 0
modprobe: [tran_touch-INFO]flod_main_device_init 942:bootmode 0 load touch !

// LCD屏opsMediator需要注册以支持TP手势功能、oled屏无需注册
modprobe: [tran_touch-INFO]ext_tp_function 195:opsMediator not support

// 检查匹配的TP IC型号
kworker/u32:2: [tran_touch-INFO]check_support_ic 315:controller[0],support_ic: ft3682g

// 加载供应商TP IC驱动成功，TP IC不唯一，视具体项目而定
kworker/u32:2: [tran_touch-INFO]match_tp_controller 441:load main controller vendor:focaltech ic:ft3682g success !!!
```

**解读**：TP驱动只在 `bootmode = 0`（normal boot）时加载；LCD屏需注册 `opsMediator`，OLED屏不需要；最终需匹配到对应的TP IC并加载vendor驱动成功。

**关注字段**：
- `bootmode`：必须为 `0`，否则TP不会加载
- `support_ic`：当前TP IC型号
- `load main controller vendor:xxx ic:xxx success !!!`：vendor驱动加载成功标志

### 2. 驱动正常工作（手指触摸）

**日志示例**：

```
// 手指触摸屏幕
irq/26-mtk-tpd: [FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (1009, 1932) touch up!
// 手指离开屏幕
irq/26-mtk-tpd: [FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (892, 1518) touch down!
```

**解读**：TP驱动中断处理函数能够正常上报触摸坐标与状态，说明驱动工作正常。

**关注字段**：
- `touch up` / `touch down`：触摸抬起/按下状态
- `P0 (x, y)`：触点坐标

### 3. 亮屏时TP口袋模式节点为1

**日志示例**：

```
// 开始亮屏，唤醒TP
binder:1192_3: [tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start

// TP从灭屏手势模式切换为亮屏模式
kworker/u32:5: [tran_touch-INFO]state_change_machine 169:[main]: TRAN_GESTURE_SUSPEND_MODE --> TRAN_ACTIVE_MODE
......
// 上层写入口袋模式节点
[tran_touch-INFO]tp_state_recovery 233:pocket state = 1
......
// 亮屏唤醒TP结束
kworker/u32:5: [tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
```

**解读**：亮屏时上层应当将 `pocket state` 节点写为 `1`，告知TP驱动进入口袋模式，驱动才会启用大面积防误触识别。

**关注字段**：
- `drm notify tp resume start` / `drm notify tp resume end`：亮屏唤醒TP的起止边界
- `state_change_machine`：状态切换日志，应从 `TRAN_GESTURE_SUSPEND_MODE` 切换到 `TRAN_ACTIVE_MODE`
- `pocket state = 1`：上层成功写入口袋模式节点（关键判定）
- `pocket state = 0`：上层未写入口袋模式（异常情况）

### 4. TP驱动上报大面积防误触

**日志示例**：

```
// 驱动上报大面积灭屏键值（不一定是 fts_pocket_state_report 输出，视vendor而定）
[FTS_TS/I]fts_pocket_state_report:Large area touch down

..........
// 屏幕熄灭，TP开始进入suspend模式
[tran_touch-INFO]nvt_disp_notifier_callback 104:[main]: drm notify tp suspends start
..........
// 屏幕熄灭，TP进入suspend模式完成
[tran_touch-INFO]nvt_disp_notifier_callback 113:[main]: drm notify tp suspends end
```

**解读**：当大面积按压被识别后，TP驱动会上报大面积灭屏键值，并伴随屏幕进入suspend流程。

**关注字段**：
- `Large area touch down`：大面积按压被识别并上报（关键判定）
- 上报函数名（如 `fts_pocket_state_report`）随vendor不同而不同
- `drm notify tp suspends start/end`：灭屏后TP进入suspend的起止

### 5. framework接收TP上报的大面积键值

**日志示例**：

```
// 接收到驱动上报的键值
WindowManager: interceptKeyBeforeQueueing keyCode = 358, down = true, policyFlags = 570425344, isWakeKey = false, isKeyGestureTriggered = false
TranPhoneWindowManagerImpl: interceptKeyTq keycode=358down = true
```

**解读**：framework层 `WindowManager` 接收到键值 `358`，并经由 `TranPhoneWindowManagerImpl` 进入策略处理。

**关注字段**：
- `keyCode = 358`：大面积灭屏对应的keycode
- `down = true`：按下事件
- `isWakeKey`：是否作为唤醒键
- `interceptKeyTq`：上层拦截处理入口
