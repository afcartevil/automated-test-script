---
name: uns-call-dialfail
description: "「拨打电话失败」UNISOC。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# UNS_CALL_DialFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 拨打电话失败
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

- **处理呼叫意图**: `CallIntentProcessor`
- **Telecom事件创建**: `Telecom.*Event.*CREATED`
- **尝试绑定到InCall服务**: `Attempting to bind to InCall`
- **创建连接服务包装器**: `Telecom.*ConnectionServiceWrapper.*creat`
- **InCall控制器连接回调**: `Telecom.*InCallController.*onConnected`
- **创建外呼连接**: `Telephony.*onCreateOutgoingConnection`
- **GSM/CDMA手机拨号**: `GsmCdmaPhone.*dial`
- **更新GSM连接状态**: `Telephony.*GsmConnection.*Update state`
- **RIL层拨号请求**: `RIL_.*REQUEST.*DIAL`
- **通知连接创建完成**: `Telecom.*notifyCreateConnectionComplete`
- **处理拨号结果**: `handleDialResult`
- **设置呼叫状态**: `Telecom.*setCallState`
- **连接事件：呼叫提醒通知**: `Telecom.*CONNECTION_EVENT.*EVENT_CALL_ALERTING_NOTIFICATION`
- **设置断开连接**: `Telecom.*SET_DISCONNECTED`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
S00D86C  09-24 14:53:51.366  1327  3983 I Telecom : UserCallIntentProcessor: sendIntentToDestination: send intent to Telecom directly.: TSI.pC(cssc)@BAA //Telecom收到拨号请求
S00D871  09-24 14:53:51.373  1327  3983 I Telecom : Event: RecordEntry TC@2: CREATED, com.sh.smart.caller;requestedAcct:none, selfMgd:false: TSI.pC(cssc)@BAA //Telecom创建Call，编号为TC@2
S00D8B3  09-24 14:53:51.439  1327  1327 I Telecom : InCallController$EmergencyInCallServiceConnection: Attempting to bind to InCall [ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl} supportsExternal? true supportsSelfMg?false], with Intent { act=android.telecom.InCallService cmp=com.sh.smart.caller/com.android.incallui.InCallServiceImpl (has extras) }: TSI.pC->CILH.sL->CILH.oQC->CM.sOCPA->CM.dSMCP->CM.dSPA(cssc)@BAA //Telecom尝试绑定InCallService
S00D909  09-24 14:53:51.496  1327  1327 I Telecom : InCallController: onConnected to ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}: ICSBC.oSC(cssc)@BAE //Telecom绑定InCallService成功，使dialer启动InCall界面
S00E43A  09-24 14:53:57.051  1327  2623 I Telecom : ConnectionServiceWrapper: createConnection([Call id=TC@2, state=CONNECTING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 4, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 4, UserHandle{0}, handle=tel:***********, vidst=A, childs(0), has_parent(false), cap=[], prop=[]], voip=false) via ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}.: TSI.pC->CIP.sNOCI->CSFM.rF(cssc)@BAA //Telecom尝试创建TelephonyConnectionService
M00E47C  09-24 14:53:57.101  4062  4062 I Telephony: onCreateOutgoingConnection, request: ConnectionRequest xxxxxxxxxxxxxxx Bundle[android.telecom.extra.START_CALL_WITH_VIDEO_STATE=0, android.telecom.extra.CALL_CREATED_TIME_MILLIS=397329, android.telecom.extra.CALL_TELECOM_ROUTING_START_TIME_MILLIS=402985, com.android.dialer.callintent.CALL_SPECIFIC_APP_DATA=[B@65f4823, ] isAdhocConf: N //TelephonyConnectionService创建
R00E48D  09-24 14:53:57.112  4062  4062 I GsmCdmaPhone: [0] dial; isEmergency=false (based on all phones) //流程走到GsmCdmaPhone拨号
R00E490  09-24 14:53:57.117  4062  4062 I GsmCdmaPhone: [0] useImsForCall=true, useOnlyDialedSimEccList=false, isEmergency=false, useImsForEmergency=false, useImsForUt=true, isUt=false, isSuppServiceCode=false, isPotentialUssdCode=false, isWpsCall=false, allowWpsOverIms=true, imsPhone=Handler (com.android.internal.telephony.imsphone.ImsPhone) {e821418}, imsPhone.isVoiceOverCellularImsEnabled()=true, imsPhone.isVowifiEnabled()=false, imsPhone.isVideoEnabled()=true, imsPhone.getServiceState().getState()=0 //GsmCdmaPhone根据useImsForCall判断是否是IMS call
R00E4ED  09-24 14:53:57.218  2501 13098 D ImsRIL  : [0279]> RIL_IMS_REQUEST_DIAL [SUB0] //ril拨号(此为IMS call打印，非IMS call不一样)
M00E534  09-24 14:53:57.257  4062  4062 V Telephony: GsmConnection: Update state from IDLE to DIALING for TC@2_1 //TelephonyConnectionService创建完成，Telephony进入dialing状态
09-24 14:53:57.309  1327  2789 I Telecom : CallsManager: setCallState CONNECTING -> DIALING, call: [Call id=TC@2, state=CONNECTING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 4, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 4, UserHandle{0}, handle=tel:***********, vidst=A, childs(0), has_parent(false), cap=[ sup_hld mut !v2a], prop=[]], voip=false: (...->CS.crCo->H.CS.crCo->H.CS.crCo.pICR)->CSW.hCCC(cap/cast)@E-E-BCU //Telecom进入dialing状态
S00E687  09-24 14:53:57.372  4062  4062 I TelecomFramework: TelephonyConnectionService: notifyCreateConnectionComplete TC@2_1: (...->CSW.hCCC)->CS.crCoC->H.CS.crCoC(cap/cast)@E-E-E-BCU //TelephonyConnectionService创建完成
M00F21C  09-24 14:53:59.710  4062  4062 V Telephony: GsmConnection: Update state from DIALING to ALERTING for TC@2_1 //收到底层呼通消息，代表对端收到来电
09-24 14:54:05.479  4062  4062 V Telephony: GsmConnection: Update state from ALERTING to ACTIVE for TC@2_1 //收到底层接通消息，代表对端接听通话
S010D97  09-24 14:54:05.483  1327  3973 I Telecom : CallsManager: setCallState DIALING -> ACTIVE, call: [Call id=TC@2, state=DIALING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 4, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 4, UserHandle{0}, handle=tel:***********, vidst=A, childs(0), has_parent(false), cap=[ sup_hld mut VTlrx VTltx VTlbi VTrrx VTrtx VTrbi], prop=[ HD]], voip=false: CSW.sA(cap)@BQQ //Telecom切换到ACTIVE状态
S011412  09-24 14:54:11.955  1327  1457 I Telecom : Event: RecordEntry TC@2: SET_DISCONNECTED, disconnected set explicitly> DisconnectCause [ Code: (LOCAL) Label: () Description: () Reason: (LOCAL) Tone: (27)  TelephonyCause: 3/-1 ImsReasonInfo: null]: CSW.sDc(cap)@BS0 //通话结束，打印挂断原因
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
