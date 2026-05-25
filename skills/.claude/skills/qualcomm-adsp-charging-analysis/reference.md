# Qualcomm ADSP Charging Reference

## 总览

这条链路要从 `usbtypec/dpm` 和 `battmngr/charger` 的边界看，而不是只盯 `TCPC IRQ`。

### `dpm` 与 `charger_detection` 的交汇（与 USB-PD skill 对齐）

| 方向 | 说明 |
|------|------|
| DPM → 充电识别 | `dpm_handle_cable_event()` 内调用 `charger_detection_notify()`，常见类型含 `CHARGER_DETECTION_TYPEC_UPDATE`；合同/供电变化可经 `charger_notify(CHARGER_EVENT_CONTRACT_UPDATE)` 影响 ICM |
| 充电识别 → 策略 | `charger_detection_event_handler()` 等根据 `TYPEC_UPDATE` / `USB_UPDATE` 调度 APSD、QC、RFC 分支 |

若 **`PortStatus`/PD 合同在 USB-PD 侧正常**，但 **`UsbPartnerType`/ICM 仍异常**，问题多半在本 skill 的 `ssdev`/`tccharger`/`ICM` 链，而不是再堆 `LPM` 日志。

最稳妥的顺序：

1. 先看 `dpm_handle_cable_event()`
2. 再看 `charger_detection`
3. 再看 `ssdev_usb_7550b`
4. 若进入 `RFC`，再看 `tc_rfc_ssdev -> tc_inf_class -> tc_dev_class -> tc_hl7139a`
5. 最后看 `ICM`

## 时间线

### 1. USB/PD 到 charger 的边界

关键函数：

- `dpm_handle_cable_event()`

作用：

- 更新 `DpmCtx.PwrMgr.PortStatus`
- `charger_detection_notify(CHARGER_DETECTION_TYPEC_UPDATE)`
- 单口 `ExternalSupplyChange` 时 `charger_notify(CHARGER_EVENT_CONTRACT_UPDATE)`

含义：

- `DPM` 是 `USB/PD -> charging` 的主桥接点

### 2. attach 后什么时候做 APSD

关键函数：

- `charger_detection_handle_charger_attach()`

规则：

- 若 `PD` 未 active
- 开 `HSUSB/PDPHY` 电源依赖
- 调 `ssdev_usb_enable_apsd_detection(..., true, rerun_cfg)`

含义：

- 插入后的第一轮 `BC1.2` 在 `charger_detection` 触发

### 3. APSD 结果在哪里判

关键函数：

- `usb_detect_partner()`

判定：

- `APSD_STATUS` 未 done：先记 `NONE`
- `APSD_RESULT_STATUS` 映射：
  - `SDP`
  - `CDP`
  - `DCP`
  - `FLOAT`
  - `QC_2P0`
  - `QC_3P0`

### 4. 慢速 BC1.2

关键场景：

- 慢插
- 当前先识别成 `FLOAT`
- 不是 `PD`
- `bRfcSlowDetectionEn` 打开

动作：

- `ssdev_usb_enable_slow_plug_detection(..., true)`
- `ssdev_usb_enable_apsd_detection(..., true, true)`

含义：

- 为支持 `RFC` 的充电器补做稳定的 `BC1.2 + RFC` 前置识别

### 5. QC/UFCS 分叉

关键函数：

- `charger_detection_handle_typec_charger_update()`

规则：

- `PD active`：关闭 `APSD`
- `DCP + PD failed/legacy + UfcsDetEn`：优先走 `UFCS`
- `DCP + PD failed/legacy + QcDetCfg`：走 `QC`

### 6. RFC 分叉

关键函数：

- `tc_rfc_detection_check()`
- `rfc_handshake_by_cp_ic()`

握手序列：

1. `DP/DM = 3.3V / 3.3V`
2. `DP/DM = 0V / 3.3V`
3. `DP/DM = 3.3V / 3.3V`
4. `pca_tfcp_get_min_voltage()` 验证 TA

成功后：

- `SSDEV_PARTNER_TC_RFC`

失败后：

- `tc_rfc_detection_check(..., false)`
- `rerun APSD`
- 必要时回退到 `QC`

## 最底层设备闭环

### 1. `tc_smb_*` 只是统一抽象

- `tc_smb_set_dp_dm()` -> `tc_set_dp_dm(dev, ...)`
- `tc_smb_i2c_trans()` -> `tc_i2c_trans(dev, ...)`

### 2. `tc_dev_class` 是函数表分发

- `tc_set_dp_dm()` -> `ftab[TC_DEV_SET_DP_DM]`
- `tc_i2c_trans()` -> `ftab[TC_DEV_I2C_TRANS]`

### 3. 当前设备是 `HL7139A`

在 `tc_hl7139a.c` 中：

- `TC_DEV_SET_DP_DM = tc_hl7139_set_dpm_level`
- `TC_DEV_GET_DP_DM = hl7139a_get_dp_dm`
- `TC_DEV_I2C_TRANS = hl7139a_i2c_trans`
- `TC_DEV_RFC_RESET = hl7139a_rfc_reset`

### 4. DPDM 电平控制

`hl7139a_set_dp_dm()`：

- 把 `dp/dm` 编码写入 `HL7139_REG19`

`hl7139a_get_dp_dm()`：

- 从 `HL7139_REG1A` 回读状态

### 5. I2C 通道开关

`hl7139a_i2c_trans()`：

- `enable=true` -> 写 `HL7139_REG19 = 0xFE`
- `enable=false` -> 写 `HL7139_REG19 = 0xFA`

含义：

- 这就是 RFC 通信通路的底层硬开关

### 6. level shift 相关证据

虽然高层没直接写 `level shift` 字样，但已看到：

- `tc_smb_i2c_trans(enable/disable)`
- `DPDM/HZ` 切换
- `HL7139A_I2C_VIL_UP`

可据此判断：

- RFC 通信链路不是常开
- 设备侧确实存在与 I2C 电平/通路切换相关的底层控制

## RFC 充电流程是否正确

当前可以确认这条主流程成立：

1. `DPM -> charger_detection`
2. `APSD` 先识别到 `DCP/FLOAT`
3. 慢插场景可触发 `slow BC1.2`
4. `RFC` 握手通过 `DVCHG/HL7139A` 控制 `DP/DM`
5. `tc_smb_i2c_trans()` 打开通信通道
6. `TFCP` 向 TA 下发 `voltage/current`
7. `ICM` 转入 `RFC` 充电分支

这条链在 `ADSP` 中已经闭环，不需要依赖 `kernel` 侧补全主逻辑。

## 最小结论模板

```markdown
## 支路
- BC1.2 / QC / UFCS / RFC

## 最早断点
- <function>

## 当前类型
- UsbPartnerType=<...>
- effective_charger_type=<...>

## RFC 深层状态
- DPDM 握手=<...>
- I2C 通道=<...>
- TFCP 通信=<...>

## ICM
- 事件=<...>
- 状态=<...>

## 结论
- 最可能根因：<1-2 行>
- 下一步验证：<函数/寄存器/日志>
```

## msm-kernel 转交（充电类型 / psy）

固件侧识别已合理，但 **kernel `usb`/`battery` power_supply** 或 **healthd** 仍异常时，对齐：

- [`qti_battery_charger.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/power/supply/qti_battery_charger.c)（`MSG_OWNER_BC`、`BC_NOTIFY_IND`）
- Transsion 扩展：`drivers/power/supply/transsion/`
- 交界总览：`qualcomm-kernel-adsp-bridge`、`qualcomm-msm-kernel-charging-supply-analysis`
