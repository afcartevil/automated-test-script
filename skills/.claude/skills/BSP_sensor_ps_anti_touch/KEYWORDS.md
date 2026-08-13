# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词如下：

```text
anti_touch_ultrasound
Sensor name="pdb"|Sensor name="anti_touch"
timesync|pdb:pre and now state|anti_touch: anti pre and now state
onSensorChanged distance|SHOW_INADVERTENTVIEW
```

## 关键日志示例与解读

### 有效性确认：排除超声距感项目

**搜索关键词**：`anti_touch_ultrasound`

**用途**：判断问题是否属于超声距感防误触项目。如果存在该关键词，应转由audio模块分析。

### 上层监听防误触

**搜索关键词**：`Sensor name="pdb"|Sensor name="anti_touch"`

**日志示例**：
```text
背部物理距感:
05-14 14:52:02.790464 13417 13417 D SensorManager: registerListenerImpl sensor={Sensor name="pdb", vendor="transsion", version=1, type=65634, maxRange=65535.0, resolution=1.0, power=0.001, minDelay=0} pid=13417 uid=1000 pkgname=com.transsion.microintelligence listener=g4.a@10134d6

正面物理距感：
05-14 14:17:20.931538 10237 10237 D SensorManager: registerListenerImpl sensor={Sensor name="anti_touch", vendor="mtk", version=1, type=65624, maxRange=65535.0, resolution=1.0, power=0.001, minDelay=0} pid=10237 uid=1000 pkgname=com.transsion.microintelligence listener=g4.a@6972883
```

**解读**：这类日志表示上层进入锁屏界面后开始监听防误触状态。`pdb` 表示背部物理距感，`anti_touch` 表示正面物理距感。

**关注字段**：
- `05-14 14:52:02.790464` / `05-14 14:17:20.931538`：开始监听的时间戳
- `Sensor name="pdb"`：背部物理距感
- `Sensor name="anti_touch"`：正面物理距感
- `registerListenerImpl`：上层已注册监听

### SCP侧口袋状态上报

**搜索关键词**：`timesync|pdb:pre and now state|anti_touch: anti pre and now state`

**日志示例**：
```text
背部物理距感：
[1120.434](0)[0] deputy.pdb:pre and now state is 0 1
//14:56:22.372016-(1120.790-1120.434)=14:56:22.016016时刻上报了进入口袋模式（1）的消息
[1120.790](0)[0] principal.timesync scp 1120790165749 host 1130464123450 offset 9676208547 tick 1120790 sched 1130480720463 android 05-14 06:56:22.372016
//此时SCP侧时间为06:56:22.372016，对应main_log里面时间：14:56:22.372016
[1121.387](0)[0] deputy.pdb:pre and now state is 1 0
//14:56:22.372016+(1121.387-1120.790)=14:56:22.969016时刻上报了退出口袋模式（0）的消息

正面物理距感：
[11330.495](0) deputy.anti_touch: anti pre and now state is 1 0
[11331.114](0) deputy.anti_touch: anti pre and now state is 0 1
[11331.180](0) principal.timesync scp 11331180209554 host 11339235964787 offset 8057788079 tick 11331180 sched 2475845551848 android 05-14 06:18:07.131226
```

**解读**：`0 1` 表示进入口袋模式，`1 0` 表示退出口袋模式。`timesync` 用于把SCP时间换算到 `main_log` 时间，通常要加8小时并结合tick差值反推。

**关注字段**：
- `pdb:pre and now state is 0 1`：背部物理距感进入口袋模式
- `pdb:pre and now state is 1 0`：背部物理距感退出口袋模式
- `anti pre and now state is 0 1`：正面物理距感进入口袋模式
- `anti pre and now state is 1 0`：正面物理距感退出口袋模式
- `principal.timesync`：时间换算基准

### 上层接收状态与UI展示

**搜索关键词**：`onSensorChanged distance|SHOW_INADVERTENTVIEW`

**日志示例**：
```text
在main_log中
05-14 14:56:22.035678 14104 14104 I KeyguardGestureManager: onSensorChanged distance:1.0  ,mProximityThreshold: 0.0  ,isTpTouch: true ,mNeedCreate: true
//main_log中在14:56:22.035678时刻收到了底层上报的状态1

05-14 14:56:22.313170 14104 14104 I KeyguardGestureManager: SHOW_INADVERTENTVIEW, VISIBLE
//main_log中在14:56:22.313170时刻开始显示防误触页面
```

**解读**：`onSensorChanged distance:1.0` 表示上层收到了口袋状态；`SHOW_INADVERTENTVIEW, VISIBLE` 表示上层真正展示了防误触界面。

**关注字段**：
- `onSensorChanged distance:1.0`：上层收到靠近状态
- `SHOW_INADVERTENTVIEW, VISIBLE`：防误触界面显示
- 对应时间戳：用于和SCP上报逐笔对齐

## 使用提示

- 必须先区分背部物理距感 `pdb` 和正面物理距感 `anti_touch`。
- 分析时以每次上层开始监听为一个候选窗口起点，不能把不同监听窗口的日志串在一起。
- 结论必须落到完整证据链：上层监听、SCP状态、main_log接收、UI展示。
