---
name: uns-call-incominganswerfail
description: "「来电接听失败」UNISOC。拉 main/system/radio 对 patterns 出结论。"
---

# UNS_CALL_IncomingAnswerFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 来电接听失败
- **特征**: 
- **平台边界**: 与 **UNISOC** 机型或 Jira 芯片字段一致时使用。

## 能做什么

指导从 `main`、`system`、`radio`（或 bugreport 对应缓冲区）中筛出与本场景相关的打印，对照 **patterns** 与 **正常参考日志**，给出结构化根因推断与验证建议。

## 怎么做

1. **取日志**: 收集 `main`、`system`、`radio`；Modem/RIL 多在 `radio`，Framework/UI 多在 `main`/`system`。
2. **检索**: 用下方 **patterns** 在三类日志中搜索；对照 **正常流程参考日志** 看是否缺阶段（log 等级可能导致缺失）。
3. **对齐 AOSP/子系统**（按现象选用）:
   - 数据/APN: `DcTracker`、`DataNetworkController`、`ApnSettings`、RIL `SETUP_DATA_CALL` / `DATA_REGISTRATION_STATE` 等。
   - SIM/信号: `ServiceStateTracker`、`SignalStrength`、`UiccController` 等。
   - 通话/短信: Call/IMS、`SmsDispatcher` / MMS 通路（依版本）。
   - 电源/背光: `DisplayPowerController`、`AutomaticBrightnessController`、`PowerManagerService` 等。
   - 稳定性: Watchdog、`ActivityManager`、`system_server` 崩溃栈。
   标出**缺失的期望阶段**、**异常 cause/返回值**、与参考序列的差异。
4. **输出结论**:
   - 现象 ↔ 关键日志（缓冲区、tag、时间线）。
   - 1–2 条最可能根因（Modem / RIL / Framework / App）。
   - 是否属于本场景典型栈；否则建议的排查/转派方向。
   - 建议复现、对比机、开关或补丁验证步骤。

## 研发关注点 (patterns)

- **AT命令收到来电RING指示**: `AT<.*RING`
- **通知新的响铃连接（来电）**: `notifyNewRingingConnection`
- **Telecom事件创建**: `Telecom.*Event.*CREATED`
- **创建连接服务包装器**: `Telecom.*ConnectionServiceWrapper.*creat`
- **创建来电连接**: `Telephony.*onCreateIncomingConnection`
- **通知连接创建完成**: `Telecom.*notifyCreateConnectionComplete`
- **来电过滤结果**: `IncomingCallFilterGraph.*result`
- **设置呼叫状态**: `Telecom.*setCallState`
- **检查勿扰模式是否关闭**: `TranCallState.*isZenModeOff`
- **尝试绑定到InCall服务**: `Attempting to bind to InCall`
- **InCall控制器连接回调**: `Telecom.*InCallController.*onConnected`
- **接听呼叫**: `DialerCall.*answer`
- **设置断开连接**: `Telecom.*SET_DISCONNECTED`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
R0096DA  09-24 14:53:27.808   748  1130 D RIL     : Channel[3] AT< +CRING: VOICE //Telephony收到来电请求
R009738  09-24 14:53:27.901  4062  4062 I Phone-1 : notifyNewRingingConnection: phoneId=[1], connection=[[ImsPhoneConnection objId: 97768613 telecomCallID: null address: [****] isAdhocConf: N ImsCall: [ImsCall objId:242942620 onHold:N mute:N mCallProfile:{ serviceType=1, callType=1, restrictCause=0, mediaProfile={ audioQuality=2, audioDirection=3, audioCodecAttribute=null, videoQuality=0, videoDirection=-1, rttMode=0, hasRttAudioSpeech=false }, emergencyServiceCategories=0, emergencyUrns=[], emergencyCallRouting=0, emergencyCallTesting=false, hasKnownUserIntentEmergency=false, mRestrictCause=0, mCallerNumberVerstat= 0, mAcceptedRtpHeaderExtensions= [] } networkType:13 updateRequest:NONE merging:N merge action pending:N merged:N multiParty:N confHost:N buried term:N isVideo: N wasVideo: N isWifi: N session:[ImsCallSession objId:153149967 callId:1] transientSession:null]]], registrants=[com.android.internal.telephony.Registrant@13902b, com.android.internal.telephony.Registrant@a83ac88] //Telephony发送来电请求通知
S009806  09-24 14:53:28.029  1327  3976 I Telecom : Event: RecordEntry TC@1: CREATED, null;null: TSI.aNIC(cap)@A1A //Telecom创建Call,编号为TC@1
S009823  09-24 14:53:28.039  1327  3976 I Telecom : ConnectionServiceWrapper: createConnection([Call id=TC@1, state=NEW, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:***********, vidst=A, childs(0), has_parent(false), cap=[], prop=[]], voip=false) via ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}.: TSI.aNIC(cap)@A1A //Telecom尝试创建TelephonyConnectionService
M0098FA  09-24 14:53:28.151  4062  4062 I Telephony: onCreateIncomingConnection, request: ConnectionRequest xxxxxxxxxxxxxxx Bundle[android.telecom.extra.INCOMING_CALL_ADDRESS=***, android.telecom.extra.CALL_SUBJECT=, android.telecom.extra.LOCATION=null, android.telecom.extra.PRIORITY=-1, android.telecom.extra.CALL_CREATED_TIME_MILLIS=373932, android.telecom.extra.CALL_TELECOM_ROUTING_START_TIME_MILLIS=373999, ] isAdhocConf: N //TelephonyConnectionService创建
S009A2D  09-24 14:53:28.343  4062  4062 I TelecomFramework: TelephonyConnectionService: notifyCreateConnectionComplete TC@1_1: (...->CSW.hCCC)->CS.crCoC->H.CS.crCoC(cap/cast)@E-E-E-A1E //TelephonyConnectionService创建完成
S009D19  09-24 14:53:28.568  1327 18307 I Telecom : IncomingCallFilterGraph: Filter com.android.server.telecom.callfiltering.CallFilter@bd20d04 done, result: [Allow, logged, notified]. //骚扰拦截检查允许来电
S009D1B  09-24 14:53:28.568  1327 18307 I Telecom : CallsManager: setCallState NEW -> RINGING, call: [Call id=TC@1, state=NEW, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:***********, vidst=A, childs(0), has_parent(false), cap=[ sup_hld mut VTlrx VTltx VTlbi spd_aud], prop=[ HD]], voip=false //Telecom切换到RINGING状态
S009D67  09-24 14:53:28.580  1327 18307 I Telecom : TranCallState: canFlash=false newState=4 isFlashOpen=false mCameraStatus=1 mFlashLightStatus=1 isNotLongBatteryMode=true isPowerSaveMode=true isNotBatteryLow=false isZenModeOff=true isGestureAnswerOff=truetag = successful incoming call //ZenMode(勿扰模式)未打开
S009DC9  09-24 14:53:28.639  1327 18307 I Telecom : InCallController$EmergencyInCallServiceConnection: Attempting to bind to InCall [ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl} supportsExternal? true supportsSelfMg?false], with Intent { act=android.telecom.InCallService cmp=com.sh.smart.caller/com.android.incallui.InCallServiceImpl } //Telecom尝试绑定InCallService
S009F57  09-24 14:53:28.866  1327  1327 I Telecom : InCallController: onConnected to ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}: ICSBC.oSC(cssc)@A2Q //Telecom绑定InCallService成功，使dialer启动InCall界面
M00ADDF  09-24 14:53:34.725  2861  2861 I Dialer  : DialerCall.answer - videoState: 0 //用户点击接听
S00ADF8  09-24 14:53:34.736  1327  2623 I Telecom : CallsManager: setCallState RINGING -> ANSWERED, call: [Call id=TC@1, state=RINGING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:***********, vidst=A, childs(0), has_parent(false), cap=[ sup_hld mut VTlrx VTltx VTlbi spd_aud], prop=[ HD]], voip=false: ICA.aC->CSFM.rF(cssc)@A4A //Telecom切到ANSWERED状态
S00AF21  09-24 14:53:34.832  1327  2784 I Telecom : CallsManager: setCallState ANSWERED -> ACTIVE, call: [Call id=TC@1, state=ANSWERED, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:***********, vidst=A, childs(0), has_parent(false), cap=[ sup_hld mut VTlrx VTltx VTlbi VTrrx VTrtx VTrbi spd_aud], prop=[ HD]], voip=false: CSW.sA(cap)@A4c //通话接通，Telecom切到ANSWERED状态
S00BCD7  09-24 14:53:43.017  1327  2189 I Telecom : Event: RecordEntry TC@1: SET_DISCONNECTED, disconnected set explicitly> DisconnectCause [ Code: (REMOTE) Label: () Description: () Reason: (NORMAL) Tone: (27)  TelephonyCause: 2/-1 ImsReasonInfo: ImsReasonInfo :: {510 : CODE_USER_TERMINATED_BY_REMOTE, 0, 999}]: CSW.sDc(cap)@A7Q //通话结束，打印挂断原因
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
