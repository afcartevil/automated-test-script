# 常见问题与原因对照表

| 序号 | 问题现象 | 日志特征 | 根因说明 |
|------|----------|----------|----------|
| 1 | 从暗环境灭屏，在亮环境亮屏，亮屏过后，屏幕亮度从暗到亮 | 首笔光感数据上报较慢，自动背光在亮屏时先使用亮屏前的历史lux值；可结合 `principal.transceiver enable: 5`、`*_als_sample`/`*_report_als`、`light value` 的时间差确认 | 第一笔数据上报较慢，导致自动背光用了亮屏前的lux值，也就是暗环境下灭屏前的一笔光感数据作为亮屏lux值 |

## 详细说明

### 问题1：从暗环境灭屏，在亮环境亮屏，亮屏过后，屏幕亮度从暗到亮

**日志特征**：
```text
1. main_log中存在自动背光注册光感日志：
   AutomaticBrightnessController
   registerListenerImpl
   OriginChannel

2. scp_log中存在enable日志，但首笔上报 `*_als_sample` 或 `*_report_als` 出现较晚。

3. main_log中 `light value` 到达HAL较晚，导致亮屏初期使用了历史lux值。
```

**根因分析**：第一笔数据上报较慢，导致自动背光用了亮屏前的lux值，也就是暗环境下灭屏前的一笔光感数据作为亮屏lux值。

**排查建议**：
- 先确认 `enable -> 首笔上报` 是否显著大于60ms。
- 再确认 `首笔上报 -> HAL收数` 是否显著大于40ms。
- 如果底层和HAL链路都偏慢，优先排查首笔上报时序。
