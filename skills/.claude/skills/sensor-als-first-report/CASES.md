# 典型案例

## 案例1：非最低亮度指纹解锁屏幕先暗后亮

### 现象

指纹解锁后有快速的先暗后亮现象。

### 分析过程

1. 在 `main_log_1__2026_0421_161456` 中确认亮屏自动背光注册sensor，注册时间为 `16:14:35.120605`，频率为 `165ms`。
2. 在 `scp_log_9__2026_0421_161456` 中搜索 `timesync|principal.transceiver enable: 5`，找到与 `16:14:35.120605` 最近的 `timesync` 为 `08:14:36.918804`（+8小时），往上推第一个频率为 `165ms` 的enable。
3. 计算enable时间：`08:14:36.918804 - (339916.776 - 339914.978) + 8小时 = 16:14:35.120804`，光感enable在注册时间之后，时序合理。
4. 在 `scp_log` 中确认enable之后第一次数据上报打印，`339915.041 - 339914.978 = 0.063 = 63ms`，满足定时器60ms触发。
5. 继续在 `main_log` 中搜索 `light value`，HAL层收到底层数据时间为 `16:14:35.189485`，与底层首笔上报的总耗时约 `69ms`，分析发现数据上报正常。

### 根因

数据上报正常，该现象不是光感首笔上报异常导致。

### 关键日志

```text
47599: 04-21 16:14:35.120605  1762  1962 D SensorManager: registerListenerImpl sensor={Sensor name="stk35f62_als", vendor="sensortek", version=1, type=5, maxRange=65535.0, resolution=1.0, power=0.001, minDelay=125000} pid=1762 uid=1000 pkgname=android listener=com.android.server.display.AutomaticBrightnessController$2@c7a4fdd
04-21 16:14:35.121171  1050  1050 I OriginChannel: batch: [5,165000000,0]

        行 1959: [339906.534](0)[0] principal.timesync scp 339906534878631 host 339916718135657 offset 10186777026 tick 339906534 sched 107001719532484 android 04-21 08:14:26.678870
        行 2348: [339909.815](0)[0] principal.transceiver enable: 5 165000000 0
        行 2378: [339909.926](0)[0] principal.transceiver enable: 5 250000000 0
        行 2494: [339910.491](0)[0] principal.transceiver enable: 52 200000000 0
        行 2842: [339912.523](0)[0] principal.transceiver enable: 5 165000000 0
        行 2921: [339912.930](0)[0] principal.transceiver enable: 5 250000000 0
        行 3001: [339913.251](0)[0] principal.transceiver enable: 52 200000000 0
        行 3281: [339914.978](0)[0] principal.transceiver enable: 5 165000000 0
        行 3360: [339915.416](0)[0] principal.transceiver enable: 5 250000000 0
        行 3438: [339915.762](0)[0] principal.transceiver enable: 52 200000000 0
        行 3657: [339916.776](0)[0] principal.timesync scp 339916776954963 host 339926958070042 offset 10186777155 tick 339916776 sched 107011959466662 android 04-21 08:14:36.918804

[339914.978](0)[0] principal.transceiver enable: 5 165000000 0
[339914.978](0)[0] deputy.TRAN_ALS stk3bfx_als_enable 2914: stk3bfx als enable.

[339915.041](0)[0] deputy.TRAN_ALS stk3bfx_als_sample 3636: : lux-als-g-scale:268 395640 134016 0.002000

04-21 16:14:35.189485  1050  1118 I HfLooper: light value = 268.000000
```

## 扩展文档

- 自动背光流程：自动背光代码流程
- Sensor MTK数据链路：Sensor_MTK数据流框架解析
