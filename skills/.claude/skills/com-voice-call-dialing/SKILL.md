---
name: com-voice-call-dialing
description: "通话拨号流程异常分析: 覆盖来电接入、去电发起、通话状态迁移、域选路(IMS/CS)与重拨、来电筛选与重定向、RTT/视频能力协商、会议通话/合并、PhoneInterfaceManager无线电/调制解调器流程的全链路分析 | 通话/拨号/来电/去电/掉话/掉线/call drop/通话中断 | 当用户报告与「通话拨号流程异常分析」相关的日志分析需求时使用"
---

# 通话拨号流程异常分析

## 适用范围

本场景用于分析 Telecom 到 Telephony 的通话建立和断开链路，重点定位问题发生在上层通话入口、Connection 创建、IMS/CS 域选择、筛选/重定向、状态迁移，还是 Radio/Modem 建链。

典型问题包括：

- 拨号失败、无法呼出、拨号后立即断开。
- 来电不响铃、无法接听、接听后掉话。
- VoLTE/IMS/CS 域选择异常。
- Call filtering / screening / redirection 超时或误拦截。
- ACTIVE 后掉话，需要分析 disconnect cause。

## 不适用场景

- 紧急号码识别、拦截或 ECC 配置问题：优先 `com-voice-ecc-emergency`。
- 仅音频无声、听筒/扬声器问题：需要音频专题，不应直接按通话建链归因。
- 数据网络不可用但通话链路无证据：转蜂窝数据/网络注册专题。

## 前置条件

### 必需日志

- `bugreport*.txt`
- `radio-log*`
- `main_log*`
- `sys_log*`
- `events-log*`
- `mainlogcat-log*`
- `systemlogcat-log*`
- `0-android_main.log*`
- `0-android_system.log*`

## 分析步骤

```text
- [ ] 识别通话类型与入口
- [ ] 检查通话建立状态迁移
- [ ] 检查 IMS/CS 域选择
- [ ] 检查来电筛选/重定向
- [ ] 检查断开原因
- [ ] 检查异常模式
```

---

## 分析前最小证据集

优先确认：

- 来电/去电/紧急/会议/RTT/视频通话类型。
- 问题号码、SIM 卡槽、运营商、VoLTE/IMS 状态。
- 发生时间点、是否弱网/无服务/漫游/飞行模式恢复。
- `radio-log*`、`main_log*`、`sys_log*` 是否覆盖拨号前后。
- 如果是掉话，必须尽量提供 disconnect cause / precise cause。

若版本只打印 I 级及以上，不能因缺少 D 级域选择细节直接判断异常；先建议 `adb shell setprop persist.log.tag D` 复测，再基于现有 I/W/E 证据输出保守结论。

---

## 快速命中判断

出现以下信号可认为命中通话流程：

- 来电：`processIncomingCallIntent`、`handleNewRingingConnection`、`RINGING`。
- 去电：`startOutgoingCall`、`onCreateOutgoingConnection`、`placeOutgoingConnection`、`DIALING`。
- 域选择：`Call Domain selection triggered`、`Call Domain Selected`、`onSelectionTerminated`。
- 接听/通话中：`performAnswer`、`ACTIVE`。
- 断开：`onDisconnect.*cause=`、`setTelephonyConnectionDisconnected`、`notifyConnectionLost`。

---

## 正常链路参考

### 去电正常链路

1. Telecom 收到拨号请求，出现 `startOutgoingCall`。
2. Telephony 创建 outgoing connection，出现 `onCreateOutgoingConnection`。
3. 域选择触发，结合 IMS/CS 能力选择通话域。
4. 域选择成功，出现 `Call Domain Selected` 或等价结果。
5. `placeOutgoingConnection` 发起拨号，状态进入 `DIALING`。
6. 网络/对端响应后进入 `ACTIVE`，或先进入 alerting/ringing 类中间态。
7. 结束时出现合理 disconnect cause，并完成状态清理。

### 来电正常链路

1. Pstn/Telephony 收到 ringing connection。
2. Telecom 处理 incoming call intent。
3. Call filtering / screening / redirection 完成且未超时误拦截。
4. `onSuccessfulIncomingCall` 出现，状态进入 `RINGING`。
5. 用户接听后执行 `performAnswer`，状态进入 `ACTIVE`。
6. 挂断或对端释放时出现合理 disconnect cause。

---

## 标准分析流程

### Step 1：识别通话类型与入口

- **目标**：区分来电、去电、紧急、会议、RTT/视频。
- **关键证据**：`processIncomingCallIntent`、`startOutgoingCall`、`onCreateOutgoingConnection`。
- **判断**：缺少入口时，只能说明通话流程入口证据不足，不能直接归因 Telephony。

### Step 2：检查通话建立状态迁移

- **目标**：确认是否完成 DIALING/RINGING 到 ACTIVE。
- **关键证据**：`DIALING`、`RINGING`、`ACTIVE`。
- **判断**：未进入 DIALING 偏拨号入口或 Connection 创建；未进入 ACTIVE 偏域选择、网络建链、来电筛选或对端释放。

### Step 3：检查 IMS/CS 域选择

- **目标**：确认域选择是否成功以及选择结果是否符合能力。
- **关键证据**：`Call Domain selection triggered`、`Call Domain Selected`、`onSelectionTerminated`。
- **判断**：域选择失败时，优先看 IMS 可用性、CS fallback、网络能力和配置。

### Step 4：检查来电筛选/重定向

- **目标**：确认来电是否被筛选、重定向或阻断。
- **关键证据**：`onCallFilteringCompleted.*timeout`、`onCallScreeningCompleted.*blocked`、`onCallRedirectionComplete`。
- **判断**：超时或 blocked 需要区分正常策略拦截和误拦截。

### Step 5：检查断开原因

- **目标**：如果出现掉话或失败，确认 disconnect cause / precise cause。
- **关键证据**：`onDisconnect.*cause=`、`setTelephonyConnectionDisconnected`、`notifyConnectionLost`。
- **判断**：ACTIVE 后断开更偏网络/Radio/Modem/IMS bearer；建链前失败更偏 Telecom/Telephony/域选择。

### Step 6：检查异常模式

- **目标**：识别常见显式异常。
- **关键证据**：`onCreateIncomingConnectionFailed`、`cannot make call`、`onFailedOutgoingCall`、`placeOutgoingConnection.*exception`。
- **判断**：显式异常优先于缺失推断；缺少某阶段日志不能单独作为错误。

---

## 常见断点地图

| 断点 | 典型证据 | 建议归因方向 |
|---|---|---|
| Telecom 入口缺失 | 无 incoming/outgoing call intent | 上层拨号入口或日志窗口问题 |
| Connection 创建失败 | `onCreateOutgoingConnection.*cannot make call` | Telephony 建链前置条件异常 |
| 域选择失败 | `onSelectionTerminated` | IMS/CS 域选择、配置、网络能力 |
| 来电筛选拦截 | filtering timeout / blocked | Call screening/redirection 策略 |
| ACTIVE 后断开 | `notifyConnectionLost` / disconnect cause | 网络、Radio、Modem、IMS bearer |

---

## 输出要求

- 开头必须说明通话类型、当前断点和最可能原因。
- 最多列 3 个原因，按可能性排序。
- 掉话类问题必须引用 disconnect cause；没有 cause 时明确证据不足。
- 缺少 radio log 时，不要直接归因 Modem，只能定位到 Framework/Telecom 层或建议补日志。

---

## 证据约束

- 没有 Telecom/Telephony 入口日志时，不能确认通话流程已经启动。
- 没有域选择结果时，不能判断 IMS/CS 选择是否正确。
- 没有 disconnect cause 时，不能确定掉话根因。
- 正常案例只用于对比链路完整性，不是当前问题事实。
