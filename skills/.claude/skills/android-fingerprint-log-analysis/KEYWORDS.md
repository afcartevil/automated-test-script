# 关键字与日志示例参考

## 关键词列表

用于日志搜索的关键词（竖线分隔，可直接用于 grep；与 SOP 原文一致）：

```
tran_fp|tran_hal||android.hardware.biometrics.fingerprint|spmt|uuid|tabin
```

## 关键日志示例与解读

### 指纹驱动加载

**日志示例**：

```
Line 10124: <6>[    5.787868][  T934] [Tran_FP][Info][tran_fp_probe][596]enter
Line 10125: <6>[    5.787874][  T934] [Tran_FP][Info][tran_fp_parse_dts_file][352] from dts pinctrl
Line 10131: <6>[    5.788042][  T934] [Tran_FP][Info][tran_fp_parse_dts_file][364] tran_fp_pinctrl_init success!
Line 10139: <6>[    5.788057][  T934] [Tran_FP][Info][tran_fp_parse_dts_file][430] parse dts success!
```

**解读**：指纹驱动加载，probe 函数执行，解析 DTS。

---

**日志示例**（中断 GPIO）：

```
Line 10141: <6>[    5.788149][  T934] [Tran_FP][Info][tran_init_eint][449]parsed irq = 58
Line 10143: <6>[    5.788152][  T934] [Tran_FP][Info][tran_init_eint][460]int gpio = 27,debounce=0
```

**解读**：中断 gpio 初始化，中断 gpio 引脚解析正常。

**关注字段**：

- `parsed irq`：分配的中断号
- `int gpio`：中断 GPIO 编号

---

**日志示例**（电源）：

```
Line 10145: <6>[    5.788560][  T934] [Tran_FP][Info][tran_fp_power_init][150]regulator-min-microvolt = 3300000 uv, regulator-max-microvolt = 3300000 uv
```

**解读**：电源初始化，设置 min-microvolt 与 max-microvolt。

---

**日志示例**（复位）：

```
Line 10147: <6>[    5.790601][  T934] [Tran_FP][Info][tran_fp_reset_gpio_low][551]GPIO 445 state is 0
Line 10174: <6>[    5.813438][  T934] [Tran_FP][Info][tran_fp_reset_gpio_high][533]GPIO 445 state is 1
```

**解读**：复位正常，复位引脚可以正常拉低与拉高。

---

**日志示例**（SPI）：

```
Line 10207: <6>[    5.823470][  T934] [Tran_FP][Info][tran_fp_probe][655][tran] set spi default state success!
```

**解读**：SPI 配置，SPI 相关引脚默认配置成功。

---

**日志示例**（netlink）：

```
Line 10217: <6>[    5.823684][  T934] [Tran_FP][Info][tran_netlink_init][759] netlink create success
Line 10219: <6>[    5.823687][  T934] [Tran_FP][Info][tran_netlink_bio_init][775] netlink_bio create success
```

**解读**：netlink 初始化成功。

---

**日志示例**（probe 成功）：

```
Line 10222: <6>[    5.823692][  T934] [Tran_FP][Info][tran_fp_probe][729]tran_fp_probe success!
```

**解读**：驱动 probe 函数执行成功。

---

**日志示例**（驱动加载耗时）：

```
Line 10226: <6>[    5.823766][  T934] BOOTPROF:      5823.766551:initcall: init_module [tran_fp_v2]    36.060616ms
```

**解读**：驱动加载耗时统计。

---

**日志示例**（TEE chip_id）：

```
Line 11387: <6>[    8.044914][  T275] Trustonic TEE: 1001(5)|[tran_spi]tran_read_goodix_chipid tran_fp goodix IC name is GW9598
```

**解读**：TEE 获取到 chip id，表明硬件正常、TA 正常（示例中为 Goodix GW9598）。

**关注字段**：

- `IC name`：传感器型号标识

---

### 指纹 HAL 初始化

**日志示例**（服务启动）：

```
Line  2555: 04-08 06:38:56.543893  1463  1463 I android.hardware.biometrics.fingerprint-service: TRANAIDL_MAIN Fingerprint HAL started
Line  2556: 04-08 06:38:56.544268  1463  1463 I android.hardware.biometrics.fingerprint-service: constructure
Line  2557: 04-08 06:38:56.544281  1463  1463 I android.hardware.biometrics.fingerprint-service: openHal
```

**解读**：指纹服务启动，HAL 初始化开始。

---

**日志示例**（设备节点）：

```
Line  2572: 04-08 06:38:56.558359  1463  1463 I [TRAN_HAL][fingerprint]: fingerprint_open
Line  2573: 04-08 06:38:56.558528  1463  1463 E [TRAN_HAL][Device]: [open] Success to open device (/dev/tran_fp) g_fd=5
```

**解读**：设备节点打开成功；HAL 与 kernel 通路正常。

**关注字段**：

- `/dev/tran_fp`：指纹设备节点路径
- `g_fd`：打开返回的文件描述符

---

**日志示例**（chip_id）：

```
Line  2646: 04-08 06:38:56.674380  1463  1463 I [TRAN_HAL][CaEntry]: [getVendorChipId]little ta chipid value = 0x00001261
Line  2647: 04-08 06:38:56.674427  1463  1463 I [TRAN_HAL][CaEntry]: [getVendorChipId]chipid = 1261, icname = GW9598
Line  2655: 04-08 06:38:56.678735  1463  1463 I [TRAN_HAL][HalContext]: [init] getVendorChipId success!
```

**解读**：HAL 成功读取 chip_id。

**关注字段**：

- `chipid`、`icname`：厂商芯片 ID 与 IC 名称

---

**日志示例**（本地 TA 路径）：

```
Line  2662: 04-08 06:38:56.679050  1463  1463 I [TRAN_HAL][CaEntry]: Using local registry: /odm/app/mcRegistry
```

**解读**：是否设置本地 TA 加载路径；后续会加载该路径下的 TA。

---

**日志示例**（HAL 版本与校准、TA 版本）：

```
Line  3430: 04-08 06:38:57.261569  1463  1463 I [TRAN_HAL][FingerprintCore]: [init] HAL Version: TRAN_HAL_V1.1
Line  3431: 04-08 06:38:57.261574  1463  1463 I [TRAN_HAL][FingerprintCore]: [init] spmt 1
Line  3432: 04-08 06:38:57.261576  1463  1463 I [TRAN_HAL][FingerprintCore]: [init] TA_VERSION V04.01.07.00
```

**解读**：`spmt` 表示指纹校准状态：`1` 已校准，`0` 未校准；`TA_VERSION` 为 TA 版本字符串。

---

**日志示例**（初始化结束与注册）：

```
Line  3585: 04-08 06:38:57.403274  1463  1673 I [TRAN_HAL][registerBinderService]: register TranssionFingerprintAIDLDaemon binder service success!
Line  3588: 04-08 06:38:57.404318  1463  1463 I android.hardware.biometrics.fingerprint-service: Fingerprint() done!
Line  3589: 04-08 06:38:57.404414  1463  1463 I AidlLazyServiceRegistrar: Registering service android.hardware.biometrics.fingerprint.IFingerprint/default
Line  6687: 04-08 06:39:05.925387  1463  1463 I AidlLazyServiceRegistrar: Process has 1 (of 1 available) client(s) in use after notification android.hardware.biometrics.fingerprint.IFingerprint/default has clients: 1
```

**解读**：指纹服务注册完成，HAL 初始化结束；AIDL 服务注册与客户端连接状态。

---

**日志示例**（指纹枚举）：

```
Line  6743: 04-08 06:39:06.097543  1463  1484 I [TRAN_HAL][fingerprint]: fingerprint_enumerate
Line  6744: 04-08 06:39:06.097567  1463  1484 I [TRAN_HAL][HalBase]: [printTargetCmdId] cmd_id = 17 (TRAN_CMD_ENUMERATE)
Line  6762: 04-08 06:39:06.103411  1463  1484 I [TRAN_HAL][FingerprintCore]: [enumerate] group_id[0]=0, finger_id[0]=0
Line  6763: 04-08 06:39:06.103458  1463  1484 I [TRAN_HAL][FingerprintCore]: [enumerate] group_id[1]=0, finger_id[1]=0
Line  6764: 04-08 06:39:06.103469  1463  1484 I [TRAN_HAL][FingerprintCore]: [enumerate] group_id[2]=0, finger_id[2]=0
Line  6765: 04-08 06:39:06.103476  1463  1484 I [TRAN_HAL][FingerprintCore]: [enumerate] group_id[3]=0, finger_id[3]=0
Line  6766: 04-08 06:39:06.103483  1463  1484 I [TRAN_HAL][FingerprintCore]: [enumerate] group_id[4]=0, finger_id[4]=0
```

**解读**：指纹枚举命令与返回的 group_id / finger_id 槽位信息。
