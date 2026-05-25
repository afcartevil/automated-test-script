# 关键字速查

## 优先关键字（不区分大小写）

| 关键字 | 适用日志 | 说明 |
|--------|----------|------|
| `power` | main_log, kernel_log | 电源状态变化，与屏幕开关及背光控制链路相关 |
| `backlight` | main_log, kernel_log | 背光设置相关打印，覆盖Framework到Kernel全链路 |
| `brightness` | main_log, kernel_log | 亮度设置节点写入和亮度值变化 |
| `aal` | main_log, kernel_log | AAL/ESS自动调光模块，影响LCD屏幕背光自动调节 |

## 显示链路补充关键字（不区分大小写）

| 关键字 | 适用日志 | 说明 |
|--------|----------|------|
| `lcm` | kernel_log | LCM（液晶模组）驱动相关，含背光设置接口 |
| `panel` | kernel_log | Panel驱动，背光命令下发 |
| `LocalDisplayAdapter` | main_log | Framework层显示适配器，负责设置背光值 |
| `led` | main_log, kernel_log | LED背光类型设备，上层通过brightness节点写入 |

## 关键日志示例与解读

### 1. Framework 设置背光

Framework 的背光范围为0~1浮点值，出现该日志表示Framework在设置背光：

```text
LocalDisplayAdapter: set backlight: 0.5227298, nits = 287.49393, sdrBacklight = 0.52273595, sdrNits = 287.49728
```

**解读**：
- `set backlight: 0.5227298` — Framework侧背光值（0~1浮点）
- `nits = 287.49393` — 对应尼特值
- `sdrBacklight` / `sdrNits` — SDR模式下的背光与尼特值

### 2. 将背光值写入设备文件

背光类型分为HWC背光和LED背光。若设备使用LED背光，上层会将背光值写入brightness节点：

```text
... write 2529 to /sys/class/leds/lcd-backlight/brightness, result: 0
```

**解读**：
- `write 2529` — 写入的背光值（整数）
- `/sys/class/leds/lcd-backlight/brightness` — 亮度sysfs节点路径
- `result: 0` — 写入结果（0表示成功）

注意：若设备使用HWC背光，背光值会随刷图一起设置，通常不会打印该日志。

### 3. Panel 驱动设置背光

背光到达底层后，通过Panel驱动的`lcm_setbacklight_cmdq`接口发送：

```text
[ 1614.525765] lcm_setbacklight_cmdq level = 939, mapped_level = 806 dimming_status = 1
```

**解读**：
- `level = 939` — 原始背光等级值
- `mapped_level = 806` — 映射后的背光等级值（经过gamma/亮度曲线映射）
- `dimming_status = 1` — 调光状态（1=调光中）

### 4. LCD 屏幕 ESS 设置背光

若屏幕类型为LCD且支持ESS背光，AAL模块会根据直方图自动调节背光。

上层AAL下发设置背光日志：

```text
04-11 06:58:05.624  1573  3743 D AalUtils: setSmartBacklightStrength(200) for (1: AAL_MODE_BALANCE, com.sh.smart.caller)
04-11 06:58:05.626  1425  1521 D AAL     : setSmartBacklightStrength: 200
04-11 06:58:05.676  1425  1512 D AAL     : 04-11 06:58:05.637 BL=3131,ESS= 256, 04-11 06:58:05.642 BL=3127,ESS= 256, 04-11 06:58:05.654 BL=3123,ESS= 256, 04-11 06:58:05.665 BL=3119,ESS= 256, 04-11 06:58:05.676 BL=3115,ESS= 256,
```

**解读**：
- `setSmartBacklightStrength(200)` — AAL智能背光强度设置为200
- `AAL_MODE_BALANCE` — AAL模式为平衡模式
- `BL=3131,ESS=256` — `BL`为背光值，`ESS`为环境智能背光补偿值

底层AAL自动设置背光日志（最终仍调用Panel驱动`lcm_setbacklight_cmdq`接口）：

```text
[20500.819509] AALMain: [name:icnl9922c_fhdp_dsi_vdo_txd_boe_120hz_lj6&][LCM] lcm_setbacklight_cmdq level = 2255, mapped_level = 1804
```

**解读**：
- `[name:icnl9922c_fhdp_dsi_vdo_txd_boe_120hz_lj6&]` — Panel名称标识
- `level = 2255, mapped_level = 1804` — AAL模块计算后的背光等级及映射值
