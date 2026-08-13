# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词如下：

```text
AutomaticBrightnessController|registerListenerImpl|OriginChannel
timesync|principal.transceiver enable: 5
lux|g_data
brightness_val
```

## 关键日志示例与解读

### 自动背光注册光感

**搜索关键词**：`AutomaticBrightnessController|registerListenerImpl|OriginChannel`

**日志示例**：
```text
04-16 11:22:20.840992 10987 11068 D SensorManager: registerListenerImpl sensor={Sensor name="stk35f62_als", vendor="sensortek", version=1, type=5, maxRange=65535.0, resolution=1.0, power=0.001, minDelay=125000} pid=10987 uid=1000 pkgname=android listener=com.android.server.display.AutomaticBrightnessController$2@3a9512

04-16 11:22:20.841424   997   997 I OriginChannel: batch: [5,165000000,0]
```

**解读**：`registerListenerImpl` 代表注册，`Sensor name="stk35f62_als"` 表示光感器件型号为 `stk35f62_als`，`AutomaticBrightnessController` 表示自动背光，`OriginChannel: batch: [5,165000000,0]` 表示下发采集频率是 `165ms`，对应的 `sensor_type` 是 `5`，也就是光感。

**关注字段**：
- `11:22:20.840992`：自动背光注册光感的时间戳
- `Sensor name="stk35f62_als"`：光感器件型号
- `type=5`：光感sensor type
- `batch: [5,165000000,0]`：采集频率 `165ms`，延迟 `0`

### SCP侧enable光感

**搜索关键词**：`timesync|principal.transceiver enable: 5`

**日志示例**：
```text
[903.474](0)[0] principal.timesync scp 903474729230 host 910300064592 offset 6826058823 tick 903474 sched 910309363400 android 04-16 03:22:16.337231
[907.978](0)[0] principal.transceiver enable: 5 165000000 0
```

**解读**：`03:22:16.337231` 为SCP侧时间戳，与 `main_log` 中的时间戳差值为8小时；`[903.474]` 与 `[907.978]` 为SCP系统启动时间戳；`principal.transceiver enable: 5` 为SCP enable光感任务打印，后面的 `5 165000000 0` 表示 `sensor_type=5`、采集频率 `165ms`、延迟 `0`。

**关注字段**：
- `principal.timesync`：用于建立SCP时间和安卓时间的换算基准
- `04-16 03:22:16.337231`：SCP侧时间戳
- `[903.474]`、`[907.978]`：SCP启动时间戳，用于回推enable时间
- `enable: 5 165000000 0`：光感enable及采样参数

### 光感原始数据与算法结果

**搜索关键词**：`lux|g_data`

**日志示例**：
```text
stk型号（屏下光感）示例日志：
//光感原始通道数据
[913.034](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2672: ch0[0]:151276, ch1[0]:156316, ch2[0]:51368, ch3[0]:468128
//光感原始数据
[913.034](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2719: : unify ori ALS = 468128, G = 156316 G_data_ratio = 156316
//屏幕信息，包括：背光、RGB
[913.035](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2803: DisplayData Brightness_2:22 R:97,G:99,B110
//算法计算过后的数据
[913.035](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2805: unify estimate ALS = 467992, G = 156269, noise ALS = 136, G = 47
//最终计算得出的光感值“g_data ”
[913.035](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2843: :dim_process cg ratio:2.994766,g_data = 15,brightness:22,als_algo_timer_count:0,brightness_st:255,g_lcm_dim_count:17

mn型号示例日志：
//上次和本次lux信息
[514746.604](0) DEPUTY.[MN7991X] lux_convert_to_lux 1810: lux_per_lux=1000, new_lpc=284, lux=94
//上报的lux值信息
[514746.604](0) DEPUTY.[MN7991X] mn7991x_report_als 1530: =====> lux=94, ir=4, als=305
```

**解读**：STK型号日志包含原始通道数据、原始ALS、屏幕背光和RGB信息、算法估算值以及最终 `g_data`；MN型号日志可直接从 `lux_convert_to_lux` 和 `mn7991x_report_als` 中获取lux值。运行期间需要持续观察这些光感值是否连续变化。

**关注字段**：
- `unify ori ALS`：原始ALS值
- `unify estimate ALS`：算法估算后的ALS值
- `g_data = 15`：最终用于自动背光判断的光感值
- `brightness:22`：SCP侧看到的背光值
- `lux=94`：MN型号光感lux值

### 上层背光写节点

**搜索关键词**：`brightness_val`

**日志示例**：
```text
04-16 11:22:20.920020   993   993 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.002930) brightness_val(12)
```

**解读**：`brightness_val(12)` 为上层写背光节点的值，需要与 `scp_log` 中的 `lux`、`g_data`、`brightness` 结合确认是否同步对应。

**关注字段**：
- `brightness(0.002930)`：归一化背光值
- `brightness_val(12)`：实际写入的背光节点值

## 使用提示

- 运行期间问题分析不是只看首笔数据，要在一次enable到下一次enable之间连续观察光感值和背光值。
- 如果 `g_data` 剧烈变化而 `brightness` 暂时不变，要结合自动背光防抖机制判断是否合理。
- 校准问题、驱动lux算法问题、上层自动背光策略问题都可能表现为亮度异常，要按链路分层定位。
