# Qualcomm ADSP USB-PD Reference

## 总览

把 Qualcomm `ADSP USB-PD` 拆成三条主线：

- `ALERT`：硬件事件从 `TCPC` 往 `LPM` 上传
- `PM_REQUEST`：策略请求从 `DPM/PPM` 往 `LPM` 下发，再把结果回传
- `ASYNC_EVENT`：`LPM` 把端口状态变化主动汇总给 `DPM/PPM`

### `dpm` 与充电 skill 的交汇

- **`dpm_handle_cable_event()`** 在更新 `DpmCtx.PwrMgr.PortStatus` 后，通常会 **`charger_detection_notify(TYPEC_UPDATE)`**，从而触发 BC1.2/QC/RFC 等识别链（详见 `qualcomm-adsp-charging-analysis`）。
- **仅当** 现象是「APSD/QC/RFC/ICM 不对」而 **TCPC/LPM/合同/CCI 已正常** 时，应切到 charging skill，避免在 `PE/PRL` 上重复消耗时间。

### `pmic_glink` 与 AP 边界

- `PPM` 经 `ppm_notify_opm()` 等路径触发 **`pmic_glink_send_notification()`**（具体消息类型以 `pmic_glink_msg.h` 为准），供 **APSS** 侧消费。
- 若 **固件侧 `DPM/PPM` 已更新** 但 **AP 无 UCSI/connector 回调**，优先查 **glink 是否发出、AP 侧是否注册/阻塞**，而非先怀疑 `PE`。

最稳妥的分析顺序：
1. 先判定问题落在哪条主线
2. 再找固定入口函数
3. 再看事件在 `TCPM/PE/PRL/DPM/PPM` 的落点
4. 最后确认是否应当走到 `pmic_glink`

## 主线一：ALERT

### 入口

- `PmicTccPlatform_Schg_PDPhy_R1_IRQ.c`
- `PmicTccStateMachine_SignalThread()`
- `PmicTccStateMachine_Main_Thread()`
- `USBPD_LPM_EVENT_ALERT`
- `tcpm_get_events_from_alert()`

### 时序

```text
PMIC PDPhy IRQ
-> PmicTccPlatform_*Irq_Cb
-> PmicTccStateMachine_SignalThread
-> PmicTccStateMachine_Main_Thread
-> TCPC status/alert 更新
-> LPM 收到 USBPD_LPM_EVENT_ALERT
-> tcpm_get_events_from_alert()
-> 分解成 TCPM/PRL_RX/PRL_TX/PRL_HR 子事件
-> PE 在后续事件驱动下继续推进
```

### 子事件落点

- `ALERT_CC_STATUS`
  - 优先看 `TCPM`
  - 关注附着/解附着、source/sink 角色、`ConnectStatus`
- `ALERT_POWER_STATUS`
  - 优先看 `TCPM`
  - 关注 `VBUS`、`PowerOpMode`、供电方向
- `ALERT_RECEIVE_SOP_MESSAGE_STATUS`
  - 落 `PRL_RX`
  - 关注 RX header、message id、SOP type
- `ALERT_TRANSMIT_SOP_MESSAGE_*`
  - 落 `PRL_TX`
  - 关注成功、失败、discard
- `ALERT_RECEIVE_HARDRESET_STATUS`
  - 落 `PRL_HR`
- `ALERT_TRANSMIT_SIGNAL_COMPLETE`
  - 常见于 hard reset / cable reset 完成
- `ALERT_RECEIVE_FAST_ROLE_SWAP`
  - 先看 `TCPM`/本地能力，再看 PE 是否承接

### 先查什么

1. `bAlertForwarding` 是否开启
2. `TCPC` 读到的 alert/status 是否真的变化
3. `tcpm_get_events_from_alert()` 是否成功展开子事件
4. 子事件是否进入对应子模块队列
5. 若只看到 IRQ 而上层没动作，优先怀疑 alert gate、状态位未清/未置、或 TCPC 本地状态没更新

## 主线二：PM_REQUEST

### 入口

- `dpm_set_request_to_lpm()`
- `RequestBuffer`
- `USBPD_LPM_EVENT_PM_REQUEST`
- `lpm_add_dpm_request_event()`
- `PE_PM_REQUEST_RTN`
- `dpm_queue_lpm_rtn4request_event()`

### 时序

```text
DPM/PPM 发起 request
-> dpm_set_request_to_lpm()
-> 写入 RequestBuffer
-> LPM 注入 USBPD_LPM_EVENT_PM_REQUEST
-> 由 TCPM/PE/本地上下文更新模块消费
-> 生成 PmReq.State 与返回结果
-> PE_PM_REQUEST_RTN
-> DPM 处理 rtn4request
-> 若属于 UCSI 命令完成，再交给 PPM 更新 CCI
```

### 常见请求

- `GET_SRC_CAP`
- `GET_SNK_CAP`
- `DR_SWAP`
- `PR_SWAP`
- `VCONN_SWAP`
- `SOFT_RESET`
- `HARD_RESET`
- `GET_PPS_STATUS`
- `FRS/LPD/TrySNK` 类使能

### `PmReq.State` 解释

- `NONE`
  - 当前没有有效 request
- `INPROGRESS`
  - 已进入执行流程
- `WAIT`
  - 暂时 defer，等条件满足后重试
- `SUCCESS`
  - 请求完成
- `FAIL`
  - 请求执行失败
- `NOT_SUPPORTED`
  - 当前状态或能力不支持该请求

### 先查什么

1. `PmReq.Type` 是否正确写入
2. 该请求应由 `PE` 还是 `TCPM` 处理
3. `PmReq.State` 是 `FAIL` 还是 `WAIT`
4. 若是 `WAIT`，排查 defer 条件而不是直接判失败
5. 返回结果是只停在 `DPM`，还是继续被 `PPM` 包装成 `CCI`

### 容易误判的点

- `GET_PPS_STATUS` 常只更新 `DPM/PwrMgr`
- 不是所有 request 完成都必然对外产生 `UCSI` 通知
- `PE` 发起状态迁移后，真正的外部状态变化可能还要靠后续 `ASYNC_EVENT`

## 主线三：ASYNC_EVENT

### 入口

- `lpm_async_event_update()`
- `lpm_async_event_update_from_tcpm()`
- `lpm_async_event_update_from_pe()`
- `USBPD_LPM2DPM_NOTIFY_PORT_STATUS_CHANGE`
- `USBPD_DPM_EVENT_LPM_ASYNC_EVENT`
- `ppm_handle_async_event_update()`

### 时序

```text
TCPM 或 PE 检测到端口状态变化
-> lpm_async_event_update_from_tcpm/pe()
-> 合成 ConnectorStatusChange 与相关状态
-> lpm_notify_dpm()
-> DPM queue async event
-> dpm_handle_cable_event()
-> PPM 更新 mailbox/CCI
-> ppm_notify_opm()
-> pmic_glink_send_notification()
```

### 来源分工

- `TCPM`
  - `ConnectStatus`
  - `PowerDirection`
  - `PowerOpMode`
  - `PartnerType`
  - 基础 attach/detach 语义
- `PE`
  - `PDO/RDO`
  - `PDContractState`
  - `BatteryChargingStatus`
  - `ExternalSupplyChange`
  - `AltMode` 相关状态

### 先查什么

1. 变化最早由 `TCPM` 还是 `PE` 产生
2. `ConnectorStatusChange` 位图是否按预期置位
3. `DPM PwrMgr.PortStatus` 是否已更新
4. `PPM` 是否允许通知：
   - `NotifyEn`
   - holdoff
   - async pending
   - `PAN` pending
5. `glink` 是否真的发出 `UCSI_NOTIFY_IND` 或相关通知

### 容易误判的点

- `DPM` 已更新不代表 `PPM` 已通知
- `PPM` 已更新 mailbox 不代表 `APSS` 立即消费
- `PAN` 与普通 connector change 可以相互阻塞或串行

## 现象到主线映射

### 插拔后没进入 PD 协商

优先看：
- `ALERT`
- `CC_STATUS`
- `POWER_STATUS`
- `bAlertForwarding`

### request 发出但没执行

优先看：
- `PM_REQUEST`
- `PmReq.Type`
- `PmReq.State`
- defer 条件

### request 成功了但 AP 看不到状态变化

优先看：
- `ASYNC_EVENT`
- `ConnectorStatusChange`
- `PPM NotifyEn`
- `pmic_glink`

### hard reset 有硬件信号但状态机没推进

优先看：
- `ALERT_RECEIVE_HARDRESET_STATUS`
- `PRL_HR`
- 之后是否重新触发 `PE/TCPM` 状态更新

### UCSI mailbox 有值但上层无感知

优先看：
- `PPM`
- `CCI`
- `ppm_notify_opm()`
- `pmic_glink_send_notification()`

## 高价值状态变量

- `bAlertForwarding`
  - `TCPM` 是否允许把 PD 相关 alert 往上送
- `PmReq.Type`
  - 当前请求类别
- `PmReq.State`
  - 当前请求执行阶段
- `RequestBuffer`
  - `DPM -> LPM` 的请求载体
- `NotifyBuffer`
  - `LPM -> DPM` 的通知载体
- `PwrMgr.PortStatus`
  - `DPM` 聚合后的端口状态
- `ConnectorStatusChange`
  - 本次 async 更新到底改了哪些位
- `CCI`
  - `PPM/UCSI` 命令完成与 connector change 指示

## 最小结论模板

```markdown
## 主线
- ALERT / PM_REQUEST / ASYNC_EVENT

## 首个断点
- <function>

## 阻塞位置
- TCPC / TCPM / PRL / PE / DPM / PPM / glink

## 关键状态
- bAlertForwarding=<...>
- PmReq.State=<...>
- ConnectorStatusChange=<...>
- NotifyEn=<...>

## 结论
- 最可能根因：<1-2 行>
- 下一步验证：<函数/状态/日志>
```

## msm-kernel 转交（PPM/UCSI 在 AP 侧）

固件侧 `PPM`/glink 已发送，但 **connector/CCI** 在 AP 仍异常时，对齐：

- [`ucsi_glink.c`](vendor/kernel_code/kernel_platform/msm-kernel/drivers/usb/typec/ucsi/ucsi_glink.c)（`MSG_OWNER_UC`）
- 交界总览：`qualcomm-kernel-adsp-bridge`、`qualcomm-msm-kernel-usb-ucsi-analysis`
