# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词：

```text
kernel_log关键词：touch|fts|cts|gtp|nvt|chsc|ilitek|tcm
补充过滤：tran_fingerprint_status|fod finger down|fod finger up
```

## 关键日志示例与解读

### 灭屏时流程

**日志示例**：

```text
//灭屏时 向tran_fingerprint_status中写1
[FTS_TS/I]fingerprint_status_write:tran_fingerprint_status = 1
[tran_touch-INFO]nvt_disp_notifier_callback 104:[main]: drm notify tp suspends start
//TP需切换至手势模式
[tran_touch-INFO]state_change_machine 166:[main]: TRAN_ACTIVE_MODE --> TRAN_GESTURE_SUSPEND_MODE
.....
[tran_touch-INFO]nvt_disp_notifier_callback 113:[main]: drm notify tp suspends end
```

**解读**：

- `tran_fingerprint_status = 1` 表示灭屏相关指纹状态已写入 TP。
- `TRAN_ACTIVE_MODE --> TRAN_GESTURE_SUSPEND_MODE` 表示 TP 已从亮屏正常模式切到手势待机模式。
- 若未看到状态写入或未切到手势模式，需要优先怀疑 TP 指纹链路未正确打开。

**关注字段**：

- `tran_fingerprint_status`：灭屏 / 录入场景下传给 TP 的指纹状态值
- `TRAN_GESTURE_SUSPEND_MODE`：灭屏后 TP 应进入的目标模式

### 设置界面录入指纹时的流程

**日志示例**：

```text
//设置中指纹录入时 向tran_fingerprint_status中写2
[FTS_TS/I]fingerprint_status_write:tran_fingerprint_status = 2

.....
[FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (527, 2207) touch down!
//上报指纹录入按下事件
[FTS_TS/I]fts_irq_handler:fod finger down
[FTS_TS/I]fts_input_report_b:[B][resolution_multiples:16] P0 (527, 2207) touch up!
//上报指纹录入抬起事件
[FTS_TS/I]fts_irq_handler:fod finger up
......
```

**解读**：

- `tran_fingerprint_status = 2` 表示系统进入设置侧指纹录入阶段。
- `fod finger down` / `fod finger up` 是 TP 检测到 FOD 按压与抬起的直接证据。
- 若录入场景下没有这组事件，通常应优先检查 TP DTS / 驱动中的 FOD 配置与对应节点。

**关注字段**：

- `tran_fingerprint_status = 2`：录入阶段的 TP 指纹状态
- `fod finger down`：FOD 按下事件
- `fod finger up`：FOD 抬起事件

### 手机亮屏解锁时的流程

**日志示例**：

```text
//亮屏开始唤醒TP
[tran_touch-INFO]nvt_disp_notifier_callback 88:[main]: drm notify tp resume start
......
//从手势模式切换为正常模式
[tran_touch-INFO]state_change_machine 166:[main]: TRAN_GESTURE_SUSPEND_MODE --> TRAN_ACTIVE_MODE
......
//亮屏唤醒结束
[tran_touch-INFO]dsp_event_callback 269:[main] drm notify tp resume end
.....
//指纹解锁按下
[FTS_TS/I]fts_irq_handler:fod finger down
.....
//指纹解锁抬起
[FTS_TS/I]fts_irq_handler:fod finger up
```

**解读**：

- `TRAN_GESTURE_SUSPEND_MODE --> TRAN_ACTIVE_MODE` 表示 TP 已从灭屏手势模式恢复到亮屏正常模式。
- 亮屏解锁阶段仍应能看到 `fod finger down` / `fod finger up`，说明 FOD 按压链路可正常工作。
- 若亮屏恢复后无 FOD 事件，需要检查 resume 时序与状态恢复。

**关注字段**：

- `TRAN_ACTIVE_MODE`：亮屏恢复后的 TP 正常工作模式
- `fod finger down`：亮屏解锁时的按压事件
- `fod finger up`：亮屏解锁时的抬起事件

## 使用提示

- 优先先看 `tran_fingerprint_status` 是否按场景写入，再看 `fod finger down/up` 是否成对出现。
- 如果存在完整的状态写入和 `fod finger down/up`，问题通常不再优先收敛到 TP 侧。
