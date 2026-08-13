# SIM Analysis Reference

## 1. 适用范围

本专题用于指导以下 SIM / UICC 相关问题的首轮分析与归因：

- 不识卡、无 SIM 卡、识卡失败
- 反复掉卡、热插拔异常
- SIM 状态异常：`ABSENT` / `NOT_READY` / `CARD_IO_ERROR` / `CARD_RESTRICTED`
- PIN / PUK 锁定、剩余次数确认
- IMSI / ICCID 等基础信息读取失败
- READY / LOADED 状态流转异常
- SIM 初始化完成后引申出的网络注册准备异常

> SIM 问题最容易犯的错，是还没搞清楚它停在“插卡检测、锁状态、READY、LOADED”的哪一步，就直接说“卡坏了”或者“软件有问题”。先找状态机断点。

---

## 2. 分析前的最小证据集

开始分析前，优先补齐这些信息：

- 现象类型：不识卡 / 掉卡 / PIN 锁 / 状态异常 / 信息为空
- 问题时间点
- 平台：MTK / SPRD / Qcom
- 软件版本、baseband 版本
- 卡槽位置、单卡/双卡场景
- 问题 SIM 卡所属运营商
- 多张 SIM 交叉验证结果
- DUT / REF 对比结果
- 视频或截图（状态栏、设置页、SIM 管理页）
- 可用日志：main_log / radio_log / system_log / modem log

### 2.1 外部因素先排除

优先做这些交叉验证：

1. 将问题 SIM 放入一台确认正常的手机，观察问题是否复现。
2. 将正常 SIM 放入问题手机，判断问题是否消失。
3. 多找几张不同运营商、不同类型的卡交叉测试。
4. 若所有卡都不识别，优先怀疑硬件、热插拔配置、Modem bootup 或底层 GPIO 配置。
5. 若只个别卡异常，更像卡磨损、接触不良、卡槽兼容性或特殊卡兼容问题。

### 2.2 推荐优先查看的日志

- **modem log / AT log**：`+ESIMS`、`+ECIND`、`ATR`、`CPIN`、`EPINC`、`XX`
- **UiccController**：`onGetIccCardStatusDone`、`updateSimState`、`ACTION_SIM_STATE_CHANGED`
- **SIMRecords**：`fetchSimRecords`、`reading EF_IMSI`、`reading EF_ICCID`、`onAllRecordsLoaded`
- **RILJ / TelephonyRegistry**：`UNSOL_RESPONSE_SIM_STATUS_CHANGED`、`notifySimStateChange`

---

## 3. 先按状态机看流程断点

SIM 问题建议统一按下面的主流程排查：

1. **插卡检测 / 热插拔事件**
2. **PIN/PUK 状态查询**
3. **卡状态获取（IccCardStatus）**
4. **READY 广播**
5. **SIM Records 文件读取**
6. **LOADED 广播**
7. **网络注册准备完成**

### 3.1 正常状态机

Android 上层的黄金路径可以简化成：

`插卡检测 -> 状态查询 -> READY -> fetchSimRecords -> onAllRecordsLoaded -> LOADED`

### 3.2 断点含义

- **停在插卡检测前**：偏硬件、卡槽、热插拔、Modem bootup
- **停在 PIN / PUK**：正常锁卡流程，先确认用户是否已解锁
- **停在 READY 前**：偏底层卡状态、I/O、限制或框架接收异常
- **READY 有、LOADED 没有**：重点看 `SIMRecords` 读卡文件过程
- **LOADED 已完成但界面仍异常**：偏框架或应用层展示问题

---

## 4. 平台关键日志速查

## 4.1 MTK

### 关键 AT / URC

- `+ESIMS: 1,12`：SIM 插卡事件（plug in）
- `+ESIMS: 1,29`：SIM 启用状态
- `AT+CPIN?`：查询 PIN / PUK 状态
- `AT+EPINC`：查询 PIN / PUK 剩余次数

### 关键上层日志

- `RmmSimCommUrc: handleSimStateChanged`
- `UiccController: onGetIccCardStatusDone`
- `ACTION_SIM_STATE_CHANGED READY`
- `ACTION_SIM_STATE_CHANGED LOADED`
- `SIMRecords: fetchSimRecords`
- `onAllRecordsLoaded`

## 4.2 SPRD

### 关键 AT / URC

- `+ECIND: 3,100`：插卡/热插拔插入
- `+ECIND: 3,2`：初始化中
- `+ECIND: 3,6,255,3`：SIM 类型信息
- `AT+XX=0 / 2`：查询 PIN1 / PUK1 剩余次数
- `+ECIND: 3,4,0`：锁定状态
- `+ECIND: 3,2,1`：初始化完成
- `+ECIND: 3,0` 或 `+ECIND: 3,5`：SIM ready

### 关键上层日志

- `UNSOL_RESPONSE_SIM_STATUS_CHANGED`
- `UiccController: updateSimState: READY`
- `ACTION_SIM_STATE_CHANGED READY / LOADED`
- `ACTION_SIM_APPLICATION_STATE_CHANGED LOADED`
- `TelephonyRegistry: notifySimStateChange: READY->LOADED`

## 4.3 Qcom

资料中给出的故障树与 MTK 基本一致，重点看：

- 热插拔：`HOTSWAP`、`INSERTED`、`REMOVED`、`onIccSwap`
- 底层识卡：`Power up` / `Power down` / `ATR`
- 上报链路：QMI 到 TELE 的识卡状态上报
- PIN 相关：`PinStorage`

---

## 5. 关键断点与日志定位方法

## 5.1 不识卡

### 先看两层是否都有事件

1. Modem 是否上报插卡：
   - MTK：`+ESIMS: 1,12`
   - SPRD：`+ECIND: 3,100`
2. UiccController / RILJ 是否收到状态变化：
   - `EVENT_ICC_STATUS_CHANGED`
   - `UNSOL_RESPONSE_SIM_STATUS_CHANGED`

### 快速判断

- **Modem 无上报**：优先怀疑卡槽、接触不良、硬件、Modem 固件异常
- **Modem 有上报，上层无响应**：偏 RIL / Uicc 框架处理问题
- **所有卡都不识别**：优先看硬件、热插拔配置、baseband 是否正常
- **只有个别卡不识别**：优先怀疑卡磨损、卡槽接触、特定卡兼容

## 5.2 PIN / PUK 锁定

### 重点日志

- `AT+CPIN?`
- `+CPIN: SIM PIN / SIM PUK`
- MTK：`AT+EPINC`
- SPRD：`AT+XX`

### 判断规则

- 这是**正常流程分支**，不是初始化失败本身
- 若用户无法解锁，需要拿 PUK，不应误判为软件故障
- 需要同时确认剩余尝试次数，避免误操作把卡彻底锁死

## 5.3 卡状态非 READY

### 重点日志

- `onGetIccCardStatusDone`
- `IccCardStatus`
- `ACTION_SIM_STATE_CHANGED READY`

### 重点状态

- `CARD_IO_ERROR`
- `CARD_RESTRICTED`
- `PIN_REQUIRED`
- `PUK_REQUIRED`

### 判断规则

- `CARD_IO_ERROR`：SIM 卡物理损坏或 I/O 读写异常
- `CARD_RESTRICTED`：运营商或卡本身限制
- 长时间到不了 READY：初始化流程中断，偏底层或卡状态处理问题

## 5.4 READY 有、信息为空 / 没有 LOADED

### 重点日志

- `SIMRecords: fetchSimRecords`
- `reading EF_IMSI`
- `reading EF_ICCID`
- `IccFileHandler: EVENT_GET_RECORD_SIZE_DONE`
- `IccFileHandler: EVENT_READ_RECORD_DONE`
- `onAllRecordsLoaded`

### 判断规则

1. 先确认系统是否已广播 `LOADED`。
2. 若 READY 有但 LOADED 没有，重点查 `SIMRecords` 文件读取中断点。
3. 若 `EF_IMSI / EF_ICCID` 读取失败，优先怀疑卡文件不可读、卡损坏或 I/O 异常。
4. 若 `onAllRecordsLoaded` 已完成，但界面信息仍空，偏上层显示链路。

---

## 6. Modem 侧专用故障树

## 6.1 先确认 Modem 是否正常 bootup

客户报“不识卡”时，先看关于手机里是否有 **baseband 版本信息**。

- 没有 baseband：先别急着分析 SIM，本质可能是 Modem 没起来
- 有 baseband：再继续看识卡流程

## 6.2 SIM 检卡核心流程

根据资料，SIM 检卡在 Modem 侧完成，典型顺序为：

1. 给 SIM 卡上电（通常先 1.8V，失败后可切 3.0V）
2. 控制器拉 `RST`
3. SIM 卡返回 `ATR`（Answer To Reset）
4. 驱动收到 ATR 后继续后续通信

### 断点含义

- **没有收到 ATR**：多数是硬件问题
- **收到 ATR 但 ATR 不符合规范**：多为卡异常、磨损、接触问题
- **收到 ATR，后续通信反复异常**：常见于干扰或特定卡槽问题

## 6.3 热插拔配置异常

若开机检卡拿到了 ATR，但后面马上出现拔卡信息，需要重点确认：

- 机型是否真的支持热插拔
- 热插拔是否应关闭却未关闭
- 中断电平 polarity 是否配置反了

资料明确指出：

- 不支持热插拔时，应关闭该功能
- 支持热插拔但仍异常时，需检查中断电平配置是否与“拔卡后电平”一致

## 6.4 硬件进一步验证建议

若以上仍无法定位，可请硬件侧继续确认：

- `vsim / rst / io` 三路波形是否正常
- 是否存在贴电容、线路异常、卡槽与 RF 干扰问题
- `codegen.dws` 中 SIM GPIO（rst / io / clk）配置是否正确

---

## 7. 场景化分析打法

## 7.1 手机完全不识卡

### 分析步骤

1. 先看 baseband 是否正常。
2. 查 Modem 是否有插卡事件上报。
3. 查上层是否收到了 `EVENT_ICC_STATUS_CHANGED / UNSOL_RESPONSE_SIM_STATUS_CHANGED`。
4. 交叉验证多张卡、不同卡槽、不同手机。
5. 若所有卡都失败，转硬件 / 热插拔 / GPIO 配置方向。

### 常见归因

- **硬件/卡槽问题**
- **Modem 未正常启动**
- **热插拔配置错误**
- **RIL/Uicc 未正确处理状态变更**

## 7.2 需要输入 PIN / PUK

### 分析步骤

1. 查 `AT+CPIN?` 返回值。
2. 查剩余次数命令返回。
3. 确认用户是否已正确输入 PIN。

### 常见归因

- **正常锁卡流程**
- **用户无 PUK 无法解锁**
- **误把锁卡流程当作不识卡**

## 7.3 READY 前中断

### 分析步骤

1. 查 `onGetIccCardStatusDone` 中的 `IccCardStatus`。
2. 重点关注 `CARD_IO_ERROR / CARD_RESTRICTED`。
3. 看是否有 `ACTION_SIM_STATE_CHANGED READY`。

### 常见归因

- **卡物理损坏或 I/O 异常**
- **运营商限制**
- **框架状态流转异常**

## 7.4 READY 有但信息为空

### 分析步骤

1. 查是否广播 `LOADED`。
2. 查 `SIMRecords` 是否开始读 `EF_IMSI / EF_ICCID`。
3. 查 `onAllRecordsLoaded` 是否完成。

### 常见归因

- **SIM 文件读取失败**
- **卡某个 EF 文件不可读**
- **上层展示未正确消费 LOADED 后的信息**

## 7.5 反复掉卡 / 某卡槽识别不稳定

### 分析步骤

1. 查是否反复出现插卡、拔卡、重新检卡日志。
2. 查是否收到 ATR 后又多次重试通信。
3. 关注问题是否只发生在某个卡槽、某个运营商卡。

### 常见归因

- **干扰导致后续通信异常**
- **卡槽接触问题**
- **特定卡槽靠近 RF，易受干扰**
- **热插拔配置错误导致误报拔卡**

---

## 8. 典型归因矩阵

| 现象 | 先看哪里 | 常见归因 |
| --- | --- | --- |
| 完全不识卡 | `+ESIMS / +ECIND` | 硬件、卡槽、Modem 未启动、热插拔配置问题 |
| 需要 PIN / PUK | `AT+CPIN?` + 次数查询 | 正常锁卡流程、用户无 PUK |
| 状态停在非 READY | `IccCardStatus` | `CARD_IO_ERROR` / `CARD_RESTRICTED` / 初始化中断 |
| READY 有但信息为空 | `SIMRecords` + `onAllRecordsLoaded` | EF 文件读取失败、I/O 异常、上层展示问题 |
| 反复掉卡 / 某卡槽不稳 | `ATR` + 热插拔日志 | 接触不良、干扰、热插拔 polarity 错误 |
| 所有卡都不识别 | baseband + 多卡交叉验证 | Modem bootup 异常、硬件配置问题 |

---

## 9. 输出建议

对外输出时，建议按下面的口径组织：

1. **先说明流程停在哪一步**：插卡检测 / PIN / READY / LOADED。
2. **明确是底层卡通信问题，还是上层状态展示问题。**
3. **对“卡坏了”保持克制**：除非已经通过 ATR、EF 读取、多机对比等证据支撑。
4. **若涉及热插拔或 GPIO 配置**，应明确建议硬件协同验证。

---

## 10. 当前资料边界

当前专题已经覆盖：

- MTK / SPRD 的标准识卡状态机
- READY / LOADED 分层判断
- PIN / PUK 基本排查
- ATR / 热插拔 / 干扰类 Modem 故障树
- Qcom 的关键排查入口

当前资料对 eSIM、复杂多应用卡、STK 业务、UICC 协议细节的覆盖仍有限，后续可通过 V2 培训资料继续补强。 
