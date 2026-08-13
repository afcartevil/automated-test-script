# 典型案例

## 案例1：双击屏幕未亮屏

### 现象

开启 TP 双击手势功能后双击屏幕，屏幕不亮。

### 分析过程

1. 先确认 TP 双击手势已开启。
2. 再确认灭屏时 TP 已进入手势模式。
3. 在 `main_log` 中检查双击亮屏是否被口袋模式拦截。

### 根因

距离传感器未校准，系统错误进入了口袋模式。

### 关键日志

```text
TranDoubleTapGesture: doubleTapWakePocketModeListener onPocketModeChanged: true
```

## 案例2：音乐手势未生效

### 现象

播放音乐的手势无法生效，未将暂停的音乐继续播放。

### 分析过程

1. 确认 TP 驱动正常工作。
2. 确认对应音乐手势值码已开启。
3. 确认灭屏 TP 已进入手势模式。
4. 确认点击屏幕后已上报具体 TP 手势值码。
5. 在 framework 中检查 `dispatchTPGesture` 的处理结果。

### 根因

系统音乐播放状态未更新，播放音乐的操作被拦截。

### 关键日志

```text
KeyguardGestureManager: music gesture, check music active true, mCurrentGestrue = play_000
```
