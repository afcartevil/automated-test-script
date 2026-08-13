# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词如下：

```text
AutomaticBrightnessController|registerListenerImpl|OriginChannel
timesync|principal.transceiver enable: 5
*_als_sample|*_report_als
light value
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

### SCP侧首笔光感上报

**搜索关键词**：`*_als_sample|*_report_als`

**日志示例**：
```text
stk型号光感：
[908.039](0)[0] deputy.TRAN_ALS stk3bfx_als_sample 3632: : lux-als-g-scale:12 404008 129258 0.000100

mn型号光感：
[514746.604](0) DEPUTY.[MN7991X] mn7991x_report_als 1530: =====> lux=94, ir=4, als=305
```

**解读**：`[908.039]` 为前置时间戳，与最近 `timesync` 的前置时间戳差值可计算实际上报时间；`stk3bfx_als_sample` 为 `stk3bfx` 型号的上报函数，`lux-als-g-scale:12` 表示上报的光感值为 `12lux`；`mn7991x_report_als` 为 `mn7991x` 型号的上报函数，`lux=94` 表示上报的光感值为 `94lux`。

**关注字段**：
- `[908.039]`：首笔上报对应的SCP启动时间戳
- `stk3bfx_als_sample` / `mn7991x_report_als`：首笔上报函数名
- `lux-als-g-scale:12`：STK型号上报的lux值
- `lux=94`：MN型号上报的lux值

### HAL收到光感数据

**搜索关键词**：`light value`

**日志示例**：
```text
04-16 11:22:20.940225   997  1133 I HfLooper: light value = 12.000000
```

**解读**：`11:22:20.940225` 为HAL层收到SCP发送光感值的时间戳，`light value = 12.000000` 表示HAL收到的光感值为 `12lux`。

**关注字段**：
- `11:22:20.940225`：HAL收数时间戳
- `light value = 12.000000`：HAL收到的光感值

## 使用提示

- 先从 `main_log` 提取注册时间和采样频率，再到 `scp_log` 计算enable和首笔上报时间。
- `timesync` 是时间换算基准，缺少它时需要在相邻区间内谨慎估算。
- 首笔上报是否异常，要同时看 `enable -> 首笔上报` 和 `首笔上报 -> HAL收数` 两段时延。
