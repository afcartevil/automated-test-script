---
name: mtk-call-incominganswerfail
description: "「来电接听失败」MTK。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# MTK_CALL_IncomingAnswerFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 来电接听失败
- **特征**: 
- **平台边界**: 与 **MTK** 机型或 Jira 芯片字段一致时使用。
- **补充**: 无法收到来电或者来电无法正常接通

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

- **来电响铃事件检测**: `EVENT_CALL_RING`
- **检测新来电连接**: `notifyNewRingingConnection`
- **来电事件创建**: `Telecom.*Event.*CREATED`
- **连接服务包装器创建**: `Telecom.*ConnectionServiceWrapper.*creat`
- **电话模块创建来电连接**: `Telephony.*onCreateIncomingConnection`
- **连接创建完成通知**: `Telecom.*notifyCreateConnectionComplete`
- **来电过滤处理结果**: `IncomingCallFilterGraph.*result`
- **设置通话状态**: `Telecom.*setCallState`
- **勿扰模式检测**: `isNeedDisturb`
- **绑定到通话界面**: `Attempting to bind to InCall`
- **通话控制器连接成功**: `Telecom.*InCallController.*onConnected`
- **拨号应用接听**: `DialerCall.*answer`
- **来电接听操作**: `Telecom.*AnswerRinging`
- **通话设置为已挂断**: `Telecom.*SET_DISCONNECTED`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
09-24 14:53:58.257287  2673  2673 D Phone-1 : Event EVENT_CALL_RING Received state=IDLE //Telephony收到来电请求
09-24 14:53:58.299244  2673  2673 I Phone-1 : notifyNewRingingConnection: phoneId=[1], connection=[[ImsPhoneConnection objId: 167206028 telecomCallID: null address: [BFlYyvCUId8-5BXPkqC93V8lOG0] isAdhocConf: N ImsCall: [ImsCall objId:103787967 onHold:N mute:N mCallProfile:{ serviceType=1, callType=2, restrictCause=0, mediaProfile={ audioQuality=0, audioDirection=3, audioCodecAttribute=null, videoQuality=0, videoDirection=-1, rttMode=0, hasRttAudioSpeech=false }, emergencyServiceCategories=0, emergencyUrns=[], emergencyCallRouting=0, emergencyCallTesting=false, hasKnownUserIntentEmergency=false, mRestrictCause=0, mCallerNumberVerstat= 0, mAcceptedRtpHeaderExtensions= [] } networkType:13 updateRequest:NONE merging:N merge action pending:N merged:N multiParty:N confHost:N buried term:N isVideo: N wasVideo: N isWifi: N session:[ImsCallSession objId:46958558 callId:1] transientSession:null]] state:INCOMING mParent:Ringing Call], registrants=[com.android.internal.telephony.Registrant@a03b578, com.android.internal.telephony.Registrant@7af0451] //Telephony发送来电请求通知
09-24 14:53:58.336347  1550  4088 I Telecom : Event: RecordEntry TC@16: CREATED, null;null: TSI.aNIC(cap)@R0I🔒 //Telecom创建Call,编号为TC@16
09-24 14:53:58.345822  1550  4088 I Telecom-ConnectionServiceWrapper: createConnection([Call id=TC@16, state=NEW, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, childs(0), has_parent(false), mtkcap=[], mtkprop=[], cap=[], prop=[]], voip=false) via ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}.: TSI.aNIC(cap)@R0I //Telecom尝试创建TelephonyConnectionService
09-24 14:53:58.420918  2673  2673 I Telephony: onCreateIncomingConnection, request: ConnectionRequest xxxxxxxxxxxxxxx Bundle[android.telecom.extra.INCOMING_CALL_ADDRESS=***, android.telecom.extra.CALL_SUBJECT=, mediatek.telecom.extra.EXTRA_INCOMING_GWSD=false, android.telecom.extra.LOCATION=null, android.telecom.extra.PRIORITY=-1, android.telecom.extra.CALL_CREATED_TIME_MILLIS=97972674, android.telecom.extra.CALL_TELECOM_ROUTING_START_TIME_MILLIS=97972690, ] isAdhocConf: N //TelephonyConnectionService创建
09-24 14:53:58.492788  2673  2673 I TelecomFramework: TelephonyConnectionService: notifyCreateConnectionComplete TC@16_1: (...->CSW.hCCC)->CS.crCoC->H.CS.crCoC(cap/cast)@E-E-E-R0Q //TelephonyConnectionService创建完成
09-24 14:53:58.576701  1550 31466 I Telecom : IncomingCallFilterGraph: Filter com.android.server.telecom.callfiltering.CallFilter@ed85b16 done, result: [Allow, logged, notified]. //骚扰拦截检查允许来电
09-24 14:53:58.578045  1550 31466 I Telecom-CallsManager: setCallState NEW -> RINGING, call: [Call id=TC@16, state=NEW, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, childs(0), has_parent(false), mtkcap=[ sup_hld mut spd_aud], mtkprop=[ m_volte], cap=[ sup_hld mut spd_aud], prop=[]], voip=false //Telecom切换到RINGING状态
09-24 14:53:58.579089  1550 31466 I Telecom : TranCallState: isNeedDisturbfalse //isNeedDisturb(勿扰模式)未打开
09-24 14:53:58.623873  1550 31466 I Telecom-InCallController$EmergencyInCallServiceConnection: Attempting to bind to InCall [ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl} supportsExternal? true supportsSelfMg?false], with Intent { act=android.telecom.InCallService cmp=com.sh.smart.caller/com.android.incallui.InCallServiceImpl } //Telecom尝试绑定InCallService
09-24 14:53:58.703295  1550  1550 I Telecom-InCallController: onConnected to ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}: ICSBC.oSC(cssc)@R0Y //Telecom绑定InCallService成功，使dialer启动InCall界面
09-24 14:54:04.114520  4302  4302 I Dialer  : DialerCall.answer - videoState: 0 //用户点击接听
09-24 14:54:04.116688  1550  2346 I Telecom-CallsManager: holdActiveAndAnswerRinging, newCall: [Call id=TC@16, state=RINGING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, childs(0), has_parent(false), mtkcap=[ sup_hld mut spd_aud], mtkprop=[ m_volte], cap=[ sup_hld mut spd_aud], prop=[]], voip=false, activeCall: null: ICA.aC(cssc)@R14 //Telecom收到接听命令
09-24 14:54:04.130427  1550  2901 I Telecom-CallsManager: setCallState RINGING -> ANSWERED, call: [Call id=TC@16, state=RINGING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, childs(0), has_parent(false), mtkcap=[ sup_hld mut spd_aud], mtkprop=[ m_volte], cap=[ sup_hld mut spd_aud], prop=[]], voip=false: ICA.aC->CSFM.rF(cssc)@R14 //Telecom切到ANSWERED状态
09-24 14:54:04.234185  1550  3022 I Telecom-CallsManager: setCallState ANSWERED -> ACTIVE, call: [Call id=TC@16, state=ANSWERED, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 2, UserHandle{0}, handle=tel:*********73, vidst=A, childs(0), has_parent(false), mtkcap=[ sup_hld mut VTlrx VTltx VTlbi VTrrx VTrtx VTrbi spd_aud paus_VT], mtkprop=[ m_volte], cap=[ sup_hld mut VTlrx VTltx VTlbi VTrrx VTrtx VTrbi spd_aud paus_VT], prop=[]], voip=false: CSW.sA(cap)@R2M //通话接通，Telecom切到ANSWERED状态
09-24 14:54:11.582772  1550  

…(已截断，完整内容见源 JSON 对应记录的 normal_log)…
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
