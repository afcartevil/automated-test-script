# 常见问题与原因对照表

| 序号 | 问题现象 | 日志特征 | 根因说明 |
|---|---|---|---|
| 1 | 双击唤醒失效、双击亮屏失效 | `TranDoubleTapGesture: doubleTapWakePocketModeListener onPocketModeChanged: true` | 未校准距离传感器 |
| 2 | 双击唤醒失效、双击亮屏失效 | `[tran_touch-INFO]state_change_machine 166:[main]: TRAN_ACTIVE_MODE --> TRAN_SUSPEND_MODE` | 系统或驱动未开启手势功能 |
| 3 | 概率性双击不能亮屏 | BUG 单标题中明确是概率性双击亮屏失败 | 固件未适配，需要联系供应商修改固件 |
| 4 | 音乐手势失效 | TP 已开启手势并上报，但 framework 侧出现 `music gesture, check music active true, mCurrentGestrue = play_000` | 系统媒体播放已暂停，但音乐播放状态 flag 未更新，导致 TP 播放音乐手势被拦截 |

## 详细说明

### 问题1：双击屏幕未亮屏 - 口袋模式拦截

**问题描述**：

- 双击唤醒失效
- 双击亮屏失效

**日志特征**：

```text
TranDoubleTapGesture: doubleTapWakePocketModeListener onPocketModeChanged: true
```

**根因分析**：

- 系统检测到当前处于口袋模式，双击亮屏事件被拦截。
- SOP 对应根因：未校准距离传感器。

**排查建议**：

- 优先校准距离传感器。
- 参考记录：`LK6OS16-1516`

### 问题2：双击屏幕未亮屏 - 未进入手势模式

**问题描述**：

- 双击唤醒失效
- 双击亮屏失效

**日志特征**：

```text
[tran_touch-INFO]state_change_machine 166:[main]: TRAN_ACTIVE_MODE --> TRAN_SUSPEND_MODE
```

**根因分析**：

- 灭屏后 TP 进入了普通 `TRAN_SUSPEND_MODE`，而不是手势模式。
- SOP 对应根因：系统或驱动未开启手势功能。

**排查建议**：

- 先确认设置侧是否打开灭屏手势。
- 再检查驱动中是否存在对应 `gesture_data_write ... enable[1]` 日志。
- 参考记录：`X6858OS16-140`

### 问题3：概率性双击不能亮屏 - 固件未适配

**问题描述**：

- BUG 单标题中出现“概率不能双击亮屏”等描述

**日志特征**：

```text
BUG单标题中出现概率不能双击亮屏
```

**根因分析**：

- SOP 明确指出该类问题通常与固件相关，需要联系供应商修改固件。

**排查建议**：

- 对比相同机型不同固件版本表现。
- 联系供应商确认固件适配情况。
- 参考链接：[LK6OS16-451](http://jira.transsion.com/browse/LK6OS16-451)

### 问题4：音乐手势未生效

**问题描述**：

- 音乐手势失效

**日志特征**：

```text
[tran_touch-INFO]gesture_data_write 289:gesture_data_write code1[ab] enable[1]
[tran_touch-INFO]GestureIdTranslate 374:[GESTURE]g_gtp_gesture=0xab
[tran_touch-INFO]GestureHandle 426:[GESTURE]gesture report KEY_F13 done !
KeyguardGestureService: onStartCommand method=dispatchTPGesture
KeyguardGestureManager: dispatchTPGesture--->
KeyguardGestureManager: dispatchTPGesture---a[0]---= 171
KeyguardGestureManager: music gesture, check music active true, mCurrentGestrue = play_000
```

**根因分析**：

- TP 驱动已正常工作。
- 对应音乐手势值码已开启，灭屏已进入手势模式，点击屏幕后也已上报具体手势键值。
- 到 framework 侧时，音乐播放状态 flag 未更新，导致播放音乐手势被拦截。

**排查建议**：

- 将问题从 TP 驱动侧转交到 framework / 媒体状态管理链路继续分析。
- 重点检查音乐暂停后的状态同步逻辑。
