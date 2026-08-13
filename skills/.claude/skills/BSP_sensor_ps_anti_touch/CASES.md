# 典型案例

## 案例1：底层上报进入口袋模式，上层也正常显示防误触界面

### 现象

锁屏解锁界面遮挡距感后，底层识别到进入口袋模式，上层收到状态并显示防误触界面，功能表现正常。

### 分析过程

1. 在 `scp_log` 中发现 `deputy.pdb:pre and now state is 0 1`，说明底层上报进入口袋模式。
2. 结合 `principal.timesync` 将SCP时间换算到安卓时间，得到进入口袋模式时间。
3. 在 `main_log` 中找到对应时间点附近的 `KeyguardGestureManager: onSensorChanged distance:1.0`，说明上层收到状态。
4. 随后在 `main_log` 中找到 `KeyguardGestureManager: SHOW_INADVERTENTVIEW, VISIBLE`，说明上层已显示防误触界面。
5. 结论为功能正常，没有发现异常。

### 根因

该案例不是故障案例，而是标准正常链路：底层状态上报正常，上层接收正常，UI展示正常。

### 关键日志

```text
在scp_log中
[1120.434](0)[0] deputy.pdb:pre and now state is 0 1
//14:56:22.372016-(1120.790-1120.434)=14:56:22.016016时刻底层上报了进入口袋模式（1）的消息

[1120.790](0)[0] principal.timesync scp 1120790165749 host 1130464123450 offset 9676208547 tick 1120790 sched 1130480720463 android 05-14 06:56:22.372016

在main_log中
05-14 14:56:22.035678 14104 14104 I KeyguardGestureManager: onSensorChanged distance:1.0  ,mProximityThreshold: 0.0  ,isTpTouch: true ,mNeedCreate: true
//main_log中在14:56:22.035678时刻收到了底层上报的状态1

05-14 14:56:22.313170 14104 14104 I KeyguardGestureManager: SHOW_INADVERTENTVIEW, VISIBLE
//main_log中在14:56:22.313170时刻开始显示防误触页面
```

## 模块归因经验

- 如果 `scp_log` 中存在 `anti_touch_ultrasound`，说明这是超声距感防误触问题，应转audio模块。
- 如果底层存在 `0 1`，但上层没有收到 `onSensorChanged distance:1.0`，优先怀疑sensor链路传输问题。
- 如果上层收到 `distance:1.0`，但没有 `SHOW_INADVERTENTVIEW, VISIBLE`，优先转上层口袋防误触模块分析。
