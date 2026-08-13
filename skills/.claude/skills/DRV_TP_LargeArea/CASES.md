# 典型案例

## 案例1：上层问题导致大面积灭屏失效

### 现象

亮屏进入锁屏界面，手掌拍到屏幕上，无法触发大面积灭屏。

### 分析过程

1. 在 `kernel_log` 中确认TP驱动已正常加载且驱动工作正常
2. 在亮屏流程 `drm notify tp resume start` ~ `drm notify tp resume end` 之间检查 `tp_state_recovery` 输出，发现 `pocket state = 0`
3. 结论指向上层未将口袋模式节点置为 `1`

### 根因

亮屏时，上层未通知TP驱动进入口袋模式。

### 关键日志

亮屏时口袋模式节点为0：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
.....
// 亮屏过程中，上层未将口袋模式节点置1
[tran_touch-INFO]tp_state_recovery 233:pocket state = 0
........
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
```

---

## 案例2：上层成功通知进入口袋模式，TP驱动无法上报大面积防误触键值

### 现象

亮屏进入锁屏界面，手掌拍到屏幕上，无法触发大面积灭屏。

### 分析过程

1. 在亮屏流程中确认 `pocket state = 1`，说明上层已成功通知TP驱动进入口袋模式
2. 检查 `kernel_log`，未发现任何一次 `Large area touch down` 上报
3. 此时日志只能体现"驱动没收到/没上报大面积事件"的事实，**根因可能是驱动未适配（B1）或固件未适配（B2）**，需双向排查：
   - 先查驱动代码与项目宏控（B1）：归一化框架/vendor驱动是否实现并使能大面积上报路径
   - 驱动侧确认完备后再查固件能力（B2）：联系TP vendor确认固件版本是否支持大面积上报，必要时切换/升级固件复测

### 根因

驱动或固件未适配大面积防误触特性（B1：驱动侧未导入/未开启；B2：固件未上报大面积事件）。仅凭日志缺失不能直接断定为驱动问题，需结合代码与vendor确认综合定位。

### 关键日志

亮屏时上层已通知TP驱动进入口袋模式，但驱动中没有一次 Large area 键值的上报：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
.....
// 亮屏过程中，上层将口袋模式节点置1
[tran_touch-INFO]tp_state_recovery 233:pocket state = 1
........
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
.......
kernel log中未发现 "Large area touch down" 等日志输出
```

### 处理建议

- B1 方向：自查项目宏控、归一化框架与vendor驱动代码，确认大面积上报路径完备
- B2 方向：联系TP vendor，确认固件是否使能大面积识别上报，必要时升级/切换固件版本复测

---

## 案例3：固件效果不佳，偶现大面积无法灭屏

### 现象

亮屏进入锁屏界面，手掌拍到屏幕上，偶现无法触发大面积灭屏。

### 分析过程

1. TP驱动加载与基础工作正常
2. 亮屏流程中 `pocket state = 1`，上层通知正常
3. `kernel_log` 中能找到 `Large area touch down` 上报，驱动链路通畅
4. 但用户反馈问题为概率性出现，说明驱动已正常，问题落在固件效果上

### 根因

固件效果不佳，无法稳定准确识别大面积场景。

### 关键日志

kernel log中发现 `Large area touch down` 等日志输出：

```
[tran_touch-INFO]nvt_disp_notifier_callback 103:[main]: drm notify tp resume start
[tran_touch-INFO]tp_state_recovery 233:pocket state = 1
[tran_touch-INFO]dsp_event_callback 276:[main] drm notify tp resume end
......
[FTS_TS/I]fts_pocket_state_report:Large area touch down
```

### 处理建议

转 **TP_Effect 模块**，由影像同事进行固件效果优化。
