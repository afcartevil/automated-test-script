---
name: mtk-call-dialfail
description: "「拨打电话失败」MTK；通话建立慢、通话自动挂断、无SIM卡紧急呼叫、紧急号码拨打失败、未操作却自动发起通话（误拨/自动拨号）、VoWiFi视频通话连接失败、呼叫转移、呼叫等待。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# MTK_CALL_DialFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 拨打电话失败
- **特征**: 通话建立慢、通话自动挂断、无SIM卡紧急呼叫、紧急号码拨打失败、未操作却自动发起通话（误拨/自动拨号）、VoWiFi视频通话连接失败、呼叫转移、呼叫等待
- **平台边界**: 与 **MTK** 机型或 Jira 芯片字段一致时使用。
- **补充**: 拨打电话的操作失败或者流程异常

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

- **处理呼叫意图**: `CallIntentProcessor`
- **Telecom事件创建**: `Telecom.*Event.*CREATED`
- **尝试绑定到InCall服务**: `Attempting to bind to InCall`
- **创建连接服务包装器**: `Telecom.*ConnectionServiceWrapper.*creat`
- **InCall控制器连接回调**: `Telecom.*InCallController.*onConnected`
- **创建外呼连接**: `Telephony.*onCreateOutgoingConnection`
- **通知连接创建完成**: `Telecom.*notifyCreateConnectionComplete`
- **GSM/CDMA手机拨号**: `GsmCdmaPhone.*dial`
- **处理拨号结果**: `handleDialResult`
- **处理IMS呼叫状态改变**: `ImsPhoneCallTracker.*processCallStateChange.*ImsCall`
- **设置呼叫状态**: `Telecom.*setCallState`
- **连接事件：呼叫提醒通知**: `Telecom.*CONNECTION_EVENT.*EVENT_CALL_ALERTING_NOTIFICATION`
- **设置断开连接**: `Telecom.*SET_DISCONNECTED`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
09-24 14:53:19.123925  1550  2740 I Telecom-UserCallIntentProcessor: sendIntentToDestination: send intent to Telecom directly.: TSI.pC(cssc)@Rrk //Telecom收到拨号请求
09-24 14:53:19.129573  1550  2740 I Telecom : Event: RecordEntry TC@15: CREATED, com.sh.smart.caller;requestedAcct:none, selfMgd:false: TSI.pC(cssc)@Rrk🔒 //Telecom创建Call,编号为TC@15
09-24 14:53:19.192971  1550  1550 I Telecom-InCallController$EmergencyInCallServiceConnection: Attempting to bind to InCall [ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl} supportsExternal? true supportsSelfMg?false], with Intent { act=android.telecom.InCallService cmp=com.sh.smart.caller/com.android.incallui.InCallServiceImpl (has extras) }: TSI.pC->CILH.sL->CILH.oQC->CM.sOCPA->CM.dSMCP->CM.dSPA(cssc)@Rrk //Telecom尝试绑定InCallService
09-24 14:53:19.241742  1550  1550 I Telecom-InCallController: onConnected to ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}: ICSBC.oSC(cssc)@Rrs //Telecom绑定InCallService成功，使dialer启动InCall界面
09-24 14:53:25.101784  1550  2901 I Telecom-ConnectionServiceWrapper: createConnection([Call id=TC@15, state=CONNECTING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:*********82, vidst=A, childs(0), has_parent(false), mtkcap=[], mtkprop=[], cap=[], prop=[]], voip=false) via ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}.: TSI.pC->CIP.sNOCI->CSFM.rF(cssc)@Rrk //Telecom尝试创建TelephonyConnectionService
09-24 14:53:25.132517  2673  2673 I Telephony: onCreateOutgoingConnection, request: ConnectionRequest xxxxxxxxxxxxxxx Bundle[android.telecom.extra.START_CALL_WITH_VIDEO_STATE=0, android.telecom.extra.CALL_CREATED_TIME_MILLIS=97933471, android.telecom.extra.CALL_TELECOM_ROUTING_START_TIME_MILLIS=97939432, com.android.dialer.callintent.CALL_SPECIFIC_APP_DATA=[B@2c72f13, ] isAdhocConf: N //TelephonyConnectionService创建
09-24 14:53:25.143023  2673  2673 I GsmCdmaPhone: [1] dial; isEmergency=false (based on all phones) //流程走到GsmCdmaPhone拨号
09-24 14:53:25.151334  2673  2673 I GsmCdmaPhone: [1] useImsForCall=true, useOnlyDialedSimEccList=false, isEmergency=false, useImsForEmergency=false, useImsForUt=true, isUt=false, isSuppServiceCode=false, isPotentialUssdCode=false, isWpsCall=false, allowWpsOverIms=true, imsPhone=Handler (com.mediatek.internal.telephony.imsphone.MtkImsPhone) {e6eb154}, imsPhone.isVoiceOverCellularImsEnabled()=true, imsPhone.isVowifiEnabled()=false, imsPhone.isVideoEnabled()=true, imsPhone.getServiceState().getState()=0 //GsmCdmaPhone根据useImsForCall判断是否是IMS call
09-24 14:53:25.224672  2692  2692 D ImsCallSessionProxy: [callId = null] handleDialResult() success //仅IMS call会打印，底层拨打成功
09-24 14:53:25.328646  1550  4067 I Telecom-CallsManager: setCallState CONNECTING -> DIALING, call: [Call id=TC@15, state=CONNECTING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:*********82, vidst=A, childs(0), has_parent(false), mtkcap=[ sup_hld mut !v2a], mtkprop=[ m_volte], cap=[ sup_hld mut !v2a], prop=[]], voip=false: (...->CS.crCo->H.CS.crCo->H.CS.crCo.pICR)->CSW.hCCC(cap/cast)@E-E-RtU //Telecom进入dialing状态
09-24 14:53:25.468164  2673  2673 I TelecomFramework: TelephonyConnectionService: notifyCreateConnectionComplete TC@15_1: (...->CSW.hCCC)->CS.crCoC->H.CS.crCoC(cap/cast)@E-E-E-RtU //TelephonyConnectionService创建完成
09-24 14:53:27.393822  2673  2673 D ImsPhoneCallTracker: [1] processCallStateChange [ImsCall objId:46059387 onHold:N mute:N mCallProfile:{ serviceType=1, callType=2, restrictCause=0, mediaProfile={ audioQuality=0, audioDirection=1, audioCodecAttribute=null, videoQuality=0, videoDirection=-1, rttMode=0, hasRttAudioSpeech=false }, emergencyServiceCategories=0, emergencyUrns=[], emergencyCallRouting=0, emergencyCallTesting=false, hasKnownUserIntentEmergency=false, mRestrictCause=0, mCallerNumberVerstat= 0, mAcceptedRtpHeaderExtensions= [] } networkType:13 updateRequest:NONE merging:N merge action pending:N merged:N multiParty:N confHost:N buried term:N isVideo: N wasVideo: N isWifi: N session:[ImsCallSession objId:68709130 callId:[UNINITIALIZED]] transientSession:null] state=ALERTING cause=0 //仅IMS call会打印，收到底层呼通消息，代表对端收到来电，telephony的call状态切成ALERTING
09-24 14:53:27.455055  1550  3025 I Telecom : Event: RecordEntry TC@15: CONNECTION_EVENT, mediatek.telecom.event.EVENT_CALL_ALERTING_NOTIFICATION: CSW.oCE(cap)@RwE🔒 //telecom收到telephony alerting消息
09-24 14:53:34.771358  2673  2673 D ImsPhoneCallTracker: [1] processCallStateChange [ImsCall objId:46059387 onHold:N mute:N mCallProfile:{ serviceType=1, callType=2, restrictCause=0, mediaProfile={ audioQuality=0, audioDirection=3, audioCodecAttribute=null, videoQuality=0, videoDirection=-1, rttMode=0, hasRttAudioSpeech=false }, emergencyServiceCategories=0, emergencyUrns=[], emergencyCallRouting=0, emergencyCallTesting=false, hasKnownUserIntentEmergency=false, mRestrictCause=0, mCallerNumberVerstat= 0, mAcceptedRtpHeaderExtensions= [] } networkType:13 updateRequest:NONE merging:N merge action pending:N merged:N multiParty:N confHost:N buried term:N isVideo: N wasVideo: N isWifi: N session:[ImsCallSession objId:68709130 callId:1] transientSession:null] state=ACTIVE cause=0 //仅IMS call会打印，收到底层接通消息，代表对端接听来电，telephony的call状态切成ACTIVE
09-24 14:53:34.791967  1550  4067 I Telecom-CallsManager: setCallState DIALING -> ACTIVE, call: [Call id=TC@15, state=DIALING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:*********82, vidst=A, childs(0), 

…(已截断，完整内容见源 JSON 对应记录的 normal_log)…
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
