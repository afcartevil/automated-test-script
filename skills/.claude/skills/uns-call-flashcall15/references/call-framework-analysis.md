# Call Framework Analysis Reference

## 1. 适用范围

本专题用于处理更偏 **Android 上层 / Framework / Telecom / InCall / Audio** 的 Call 问题，典型包括：

- 拨号动作没有真正进入 Telecom
- 来电已上报，但无来电界面 / 无法响铃
- InCall bind 失败、界面拉起异常
- 音频路由异常（听筒 / 免提 / 蓝牙切换异常）
- 视频通话按钮、升级/降级交互异常

如果上层建链已完成，但失败发生在 SIP、HTTP、承载、网络拒绝阶段，请转 `call-protocol-ims-analysis.md`。

---

## 2. 推荐优先查看的日志

- **main_log**：Dialer、Telephony crash、界面与业务动作
- **sys_log**：Telecom 生命周期、状态流转、音频路由、InCall 绑定
- **radio_log**：来电通知、域信息、Telephony 关键事件
- **crash_log / events_log**：怀疑 crash 时重点查看

---

## 3. Framework / Android 上层完整链路

## 3.1 MO（拨号）上层关键链路

典型关键节点：

1. `CallIntentProcessor`
2. `Telecom.*Event.*CREATED`
3. `Attempting to bind to InCall`
4. `Telecom.*InCallController.*onConnected`
5. `Telecom.*ConnectionServiceWrapper.*create`
6. `Telephony.*onCreateOutgoingConnection`
7. `GsmCdmaPhone.*dial`
8. `handleDialResult`（IMS 常见）
9. `Telecom.*notifyCreateConnectionComplete`
10. `ImsPhoneCallTracker.*processCallStateChange`
11. `Telecom.*setCallState`
12. `Telecom.*CONNECTION_EVENT.*EVENT_CALL_ALERTING_NOTIFICATION`
13. `Telecom.*SET_DISCONNECTED`

## 3.2 MT（来电）上层关键链路

典型关键节点：

1. `EVENT_CALL_RING`
2. `notifyNewRingingConnection`
3. `Telecom.*Event.*CREATED`
4. `Telecom.*ConnectionServiceWrapper.*create`
5. `Telephony.*onCreateIncomingConnection`
6. `Telecom.*notifyCreateConnectionComplete`
7. `IncomingCallFilterGraph.*result`
8. `Telecom.*setCallState`
9. `Attempting to bind to InCall`
10. `Telecom.*InCallController.*onConnected`
11. `DialerCall.*answer`
12. `Telecom.*AnswerRinging`
13. `Telecom.*SET_DISCONNECTED`

---

## 4. V2 补强：雏鹰资料补充的上层链路观察点

来自 `21届雏鹰培训/第二阶段/来去电流程（上层）/来去电.txt` 与 `来电流程.txt` 的增量信息，重点用于把粗粒度节点细化为可逐跳检查的日志表。

### 4.1 MO（拨号）补强节点

在 `Telecom.*Event.*CREATED` 之前，还可以补看：

1. `DialpadFragment.*keyPressed`
2. `DialerUtils.startActivityWithErrorToast`
3. `Telecom-UserCallIntentProcessor.processOutgoingCallIntent`
4. `Telecom-CallIntentProcessor.onReceive`
5. `Telecom-NewOutgoingCallIntentBroadcaster`
6. `CallsManager.findOutgoingCallPhoneAccount / set outgoing call phone acct / dialer phone acct select`
7. `InCallController.onCallAdded`
8. `ConnectionServiceWrapper.createConnection`
9. `TelephonyConnectionService.createConnection`
10. `ImsPhone.dialInternal`

这组节点的价值：如果连 `CREATED` 前的动作都不完整，问题可能还没进入真正的 Telephony 建链阶段，而是停在 **Dialer → Telecom 入口 / 选卡 / Connection 建立前**。

### 4.2 MT（来电）补强节点

在 `notifyNewRingingConnection` 之后，可进一步细分成：

1. `PstnIncomingCallNotifier.handleNewRingingConnection`
2. `PstnIncomingCallNotifier.sendIncomingCallIntent`
3. `TelecomManager.addNewIncomingCall`
4. `TelecomServiceImpl.addNewIncomingCall`
5. `CallsManager.processIncomingCallIntent`
6. `CreateConnectionProcessor.process / attemptNextPhoneAccount`
7. `ConnectionServiceWrapper.createConnection`
8. `TelephonyConnectionService.createConnection`
9. `IncomingCallFilterGraph.performFiltering`
10. `setCallState NEW -> RINGING`
11. `InCallServiceBindingConnection.onConnected`
12. `InCallController.onConnected`

这组节点的价值：
- `notifyNewRingingConnection` 有，但 `TelecomManager.addNewIncomingCall` 之后链路断了：偏 **Telecom 来电编排**。
- 已经 `setCallState NEW -> RINGING`，但 `InCallController.onConnected` 没出现：偏 **InCall UI 绑定**。
- `InCallController.onConnected` 已出现但界面仍异常：继续看 Dialer / InCallService 消费链路。

---

## 5. 必抓的框架关键断点

### 5.1 `Telecom.*Event.*CREATED`
- 含义：Telecom 已创建这通电话，可拿到 `Call Id`
- 如果连 `CREATED` 都没有：优先怀疑拨号动作没进入 Telecom，检查入口应用、权限、拨号动作是否被拦截

### 5.2 `notifyCreateConnectionComplete`
- 含义：Telecom 与 Telephony 之间的连接已建立
- 若 `CREATED` 有、但一直没有该日志：重点看 Telecom 到 Telephony 的连接建立

### 5.3 `Attempting to bind to InCall` / `onConnected`
- 用途：确认通话界面绑定是否成功
- 只有 bind 动作、没有 `onConnected`：大概率 bind 失败，偏系统 / 进程阻塞 / InCall 服务异常

### 5.4 `setCallState` / `SET_DISCONNECTED`
- 用途：判断流程走到了哪一步，以及最后一个稳定状态
- 若已走到较后状态再断开，需要结合协议侧原因码继续判断是否转 protocol 专题

### 5.5 `CallAudio` / `CallAudioRouteStateMachine`
- 用途：响铃、听筒 / 免提 / 蓝牙切换异常排查入口

---

## 6. 场景化分析打法

## 6.1 拨号无法呼通（先看上层是否真正建链）

分析顺序：
1. 用 `Telecom.*Event.*CREATED` 拿到 `Call Id`
2. 看 `setCallState` 是否进入 `DIALING`
3. 看是否有 `notifyCreateConnectionComplete`
4. 如果 `CREATED` 前就断，继续补看第 4 章的前置拨号节点

常见归因：
- **Telecom 层阻断**：如 `CallsManager` 提示 `no available accounts`
- **Telephony crash**：`com.android.phone` 附近有 crash 栈
- **入口动作未成功发起**：Dialer → Telecom 路径中断

## 6.2 无法收到来电 / 无通话界面

分析顺序：
1. 查 `notifyNewRingingConnection`
2. 查 `Telecom.*Event.*CREATED`
3. 查 `setCallState` 是否进入 `RINGING`
4. 查 `Attempting to bind to InCall` / `onConnected`
5. 若上层来电状态正常但界面仍异常，继续看 Dialer / InCallService

常见归因：
- **系统界面链路**：来电已上报，但 InCall bind 失败，界面未拉起
- **Telecom 编排异常**：来电意图未继续下发

## 6.3 无来电铃声

重点日志：
- `CallAudio`
- `Telecom-CallAudioManager`
- `Telecom-CallAudioModeStateMachine`

判断方向：
- 是否进入 `NEW_RINGING_CALL`
- 是否请求了 `AudioFocus(RING)`
- 是否切到 `MODE_RINGTONE`

## 6.4 音频路由异常（听筒 / 免提切换）

重点日志：
- `Dialer.*setAudioRoute`
- `CallAudioRouteStateMachine`

判断思路：
- 先确认用户是否真的触发了切换动作
- 再确认 Telecom 侧收到的切换广播是否延迟或重复
- 若状态来回跳，重点看 `setSystemAudioState` 是否有额外切换
- 这类问题通常需要与音频模块联合排查

## 6.5 视频通话问题

关注点：
- 用户是否手动触发升级 / 降级
- 双卡是否支持视频通话
- 是否停在上层按钮逻辑、选卡逻辑或界面交互

重点日志：
- `CallButtonPresenter.changeToAudioClicked`
- `CallButtonPresenter.changeToVideoClicked`
- `Telecom : Event: SEND_VIDEO_REQUEST`
- `Telecom-VideoProviderProxy`
- `receiveSessionModifyResponse`
- `isVideoCallEnabled`
- `showPhoneAccountSelectionDialog`

若网络已经明确返回拒绝，再转 `call-protocol-ims-analysis.md` 继续分析。

---

## 7. 接力分析建议

当出现以下证据时，通常可以考虑交给对应方继续处理：

- `CREATED` 都没有，或 InCall bind 明显失败：接力给 **App / Framework / Dialer / Telecom**
- 问题时间点附近 `com.android.phone` crash：接力给 **Telephony**
- 音频路由逻辑异常：接力给 **Audio / System UI 协同方**

接力时至少带上：
- 问题时间点
- `Call Id`
- 断点前后的关键日志
- 录屏 / 截图
- 当前已排除项

---

## 8. 输出建议

最终输出统一复用 `SKILL.md` 的标准模板；本专题建议额外补充：
- `Domain: Framework / UI / Audio / Video`
- `Call Id`
- `Last successful step`
- `First failed / missing step`

别再单独发明模板了，模板这件事收敛一点，模型就没那么容易跑偏。
