# 详细分析步骤

## 分析流程概览

本SOP用于确认自动背光运行期间的异常是否由光感数据链路导致。用户无法提供准确问题时间时，默认进入候选观察窗口遍历模式。核心链路为：

1. 在 `main_log` 中枚举所有自动背光注册事件，生成候选注册列表。
2. 在 `scp_log` 中结合 `timesync` 和 `principal.transceiver enable: 5` 为每个候选注册匹配对应enable。
3. 以“本次enable到下一次enable之间”的区间作为一个观察窗口。
4. 在每个观察窗口内持续观察 `lux`、`g_data` 和 `brightness_val` 是否连续、是否一一对应。
5. 结合背光防抖机制判断背光延迟变化是否合理，再对所有观察窗口排序后输出结论。

## 步骤1：枚举候选注册事件

### 目标

找到所有可能与问题相关的自动背光注册事件。

### 操作

1. 打开 `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/main_log_X__XXXX_XXXX_XXXXXX`。
2. 搜索关键字：`AutomaticBrightnessController|registerListenerImpl|OriginChannel`。
3. 不要只取第一条命中结果，而是记录所有自动背光注册事件。
4. 为每条注册记录时间戳、光感器件型号、`sensor_type` 和下发频率。

### 日志示例

```text
04-16 11:22:20.840992 10987 11068 D SensorManager: registerListenerImpl sensor={Sensor name="stk35f62_als", vendor="sensortek", version=1, type=5, maxRange=65535.0, resolution=1.0, power=0.001, minDelay=125000} pid=10987 uid=1000 pkgname=android listener=com.android.server.display.AutomaticBrightnessController$2@3a9512

04-16 11:22:20.841424   997   997 I OriginChannel: batch: [5,165000000,0]
```

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 没有光感注册相关打印 | 问题出在上层 | 转单给上层 |
| 只有1条光感注册相关打印 | 直接以该注册为唯一候选 | 进入步骤2 |
| 存在多条光感注册相关打印 | 为每条注册建立候选窗口，禁止跳过 | 逐条进入步骤2 |

## 步骤2：为每个候选注册匹配观察窗口

### 目标

检查每个候选注册之后，底层SCP侧是否正常enable光感，并确定观察窗口。

### 操作

1. 打开 `mobilelog/APLog_XXXX_XXXX_XXXXXX__X/scp_log_X__XXXX_XXXX_XXXXXX`。
2. 搜索关键字：`timesync|principal.transceiver enable: 5`。
3. 对每个候选注册，利用 `timesync` 的SCP侧时间戳加8小时，大致定位上层下发注册sensor的时间点。
4. 在该时间点周围找到时间上最近且晚于注册时间的光感enable相关打印。
5. 通过 `enable` 的SCP启动时间与最近 `timesync` 的SCP启动时间戳差值，加上或减去 `timesync` 的SCP侧时间戳，换算出与 `main_log` 一致的时间戳。
6. 以“本次 `enable: 5` 到下一次 `enable: 5` 之间”的区间作为观察窗口。

### 日志示例

```text
[903.474](0)[0] principal.timesync scp 903474729230 host 910300064592 offset 6826058823 tick 903474 sched 910309363400 android 04-16 03:22:16.337231
[907.978](0)[0] principal.transceiver enable: 5 165000000 0
```

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 某个候选注册没有相关enable打印 | 该候选窗口为通信链路异常候选 | 保留该候选并继续处理其他候选 |
| 某个候选注册匹配到enable，但换算后时间早于注册时间 | 时序异常，需要重新核对timesync和匹配区间 | 继续复核该候选 |
| 某个候选注册匹配到enable，且enable时间在注册之后 | 底层已收到光感enable | 该候选进入步骤3 |

## 步骤3：逐个观察窗口检查光感值与屏幕背光是否连续和对应

### 目标

检查每个观察窗口内，光感值与屏幕背光是否连续和对应。

### 操作

1. 对每个候选窗口，在窗口起点之后开始分析，并以“本次enable到下次enable之间”的区间为观察窗口。
2. 在窗口内的 `scp_log` 中搜索关键词：`lux`、`g_data`，提取光感值。
3. 在窗口对应时间范围的 `main_log` 中搜索：`brightness_val`，提取背光值。
4. 对比同一观察窗口中的光感数据与背光值，禁止跨窗口拼接。
5. 结合STK和MN不同型号的日志格式，确认光感值是否连续变化，背光是否与之对应。
6. 若遇到 `g_data` 剧烈变化但 `brightness` 暂时不变，需要结合防抖机制判断是否合理。

### 日志示例

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

背光日志：
04-16 11:22:20.920020   993   993 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.002930) brightness_val(12)
```

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 某个观察窗口中，屏幕背光值随着光感值的变大变小同步变化 | 该观察窗口底层光感值没问题 | 保留为正常窗口并继续处理其他窗口 |
| 某个观察窗口中，屏幕背光不变，光感值变动较大 | 该观察窗口背光未跟随光感变化 | 标记为上层自动背光异常候选 |
| 某个观察窗口中，屏幕背光变动较大，光感值不变 | 该观察窗口光感与背光不对应 | 标记为上层自动背光异常候选 |

## 步骤4：对所有观察窗口排序并输出

### 目标

避免抓错场景或把不同时间段日志误拼成一个错误结论。

### 操作

1. 汇总所有观察窗口的起止时间、光感变化趋势、背光变化趋势和异常点。
2. 记录每个窗口是否存在正常防抖、校准异常、lux算法异常、上报过慢或上层自动背光不跟随等表现。
3. 按异常程度排序，优先输出证据完整且异常最明显的窗口。
4. 如果多个窗口都可疑，输出前3个候选窗口并标注对应时间范围。
5. 如果所有窗口都正常，倾向输出“非光感运行期链路问题”。

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 只有一个窗口证据最完整且异常最明显 | 可以输出单一主结论 | 输出结论 |
| 存在多个可疑窗口 | 不能下唯一绝对结论 | 输出前3个候选窗口并标注置信度 |
| 所有窗口都基本正常 | 该问题大概率不是光感运行期链路导致 | 输出结论 |

## 结论输出要点

- 明确给出 `注册时间 -> enable时间 -> 光感连续上报区间 -> 背光变化区间`。
- 说明观察窗口是“本次enable到下次enable之间”。
- 用户未提供问题时间时，必须说明总共枚举了多少个观察窗口。
- 如果存在多个可疑时间窗口，必须输出候选窗口和排序理由。
- 对STK型号优先关注 `unify ori ALS`、`unify estimate ALS`、`g_data`、`brightness`。
- 对MN型号优先关注 `lux_convert_to_lux`、`mn7991x_report_als` 中的 `lux`。
- 遇到背光延迟变化时，必须判断是否为上层防抖机制引起的合理现象。
- 结论优先落到以下几类：
  - 上层未注册，转单给上层
  - 通信链路异常，enable未下发到底层
  - 底层光感链路正常，测试环境异常
  - 上层自动背光逻辑需要确认
  - 校准问题
  - 驱动lux算法问题
  - 底层光感数据上报过慢
