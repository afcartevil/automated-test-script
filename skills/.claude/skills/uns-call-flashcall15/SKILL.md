---
name: uns-call-flashcall15
description: "「FLASH_CALL_15.XX失败」UNISOC。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# UNS_CALL_FlashCall15

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: FLASH_CALL_15.XX失败
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

- **InCall控制器连接回调**: `Telecom.*InCallController.*onConnected`
- **创建连接服务包装器**: `Telecom.*ConnectionServiceWrapper.*creat`
- **创建外呼连接**: `Telephony.*onCreateOutgoingConnection`
- **设置闪信呼叫**: `TranFlashCallController.*FlashCallHandler.*setFlashCall`
- **通知连接创建完成**: `Telecom.*notifyCreateConnectionComplete`
- **闪信呼叫提醒状态**: `TranFlashCallController.*ALERTING`
- **检查闪信呼叫**: `TranFlashCallController.*checkFlashCall`
- **设置断开连接**: `Telecom.*SET_DISCONNECTED`
- **拨号器闪信文本状态**: `Dialer.*state = 10.*flashCallText`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
S0E531F  09-18 09:50:02.174  1230  2413 I Telecom : ConnectionServiceWrapper: createConnection([Call id=TC@36, state=CONNECTING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 10, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 10, UserHandle{0}, handle=tel:**********, vidst=A, childs(0), has_parent(false), cap=[], prop=[]], voip=false) via ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}.: TSI.pC->CIP.sNOCI->CSFM.rF(cssc)@E8s //Telecom尝试创建TelephonyConnectionService
M0E536B  09-18 09:50:02.218  1765  1765 I Telephony: onCreateOutgoingConnection, request: ConnectionRequest xxxxxxxxxxxxxx Bundle[android.telecom.extra.CALL_SUBJECT=Flash_Call, android.telecom.extra.START_CALL_WITH_VIDEO_STATE=0, android.telecom.extra.CALL_TELECOM_ROUTING_END_TIME_MILLIS=910034, android.telecom.extra.CALL_CREATED_TIME_MILLIS=909962, android.telecom.extra.CALL_TELECOM_ROUTING_START_TIME_MILLIS=910033, com.android.dialer.callintent.CALL_SPECIFIC_APP_DATA=[B@1ecc50, ] isAdhocConf: N //TelephonyConnectionService创建，android.telecom.extra.CALL_SUBJECT=Flash_Call代表是flash call
M0E5383  09-18 09:50:02.227  1765  1765 D TranTele/TranFlashCallController: [FlashCallHandler][setFlashCall] telecomCallId = TC@36_1 //TranFlashCallController确认TC@36这通电话是flash call，保存该call信息
S0E570C  09-18 09:50:02.514  1230  1230 I Telecom : InCallController: onConnected to ComponentInfo{com.sh.smart.caller/com.android.incallui.InCallServiceImpl}: ICSBC.oSC(cssc)@E+o //Telecom绑定InCallService
S0E5ABE  09-18 09:50:02.960  1765  1765 I TelecomFramework: TelephonyConnectionService: notifyCreateConnectionComplete TC@36_1: (...->CSW.hCCC)->CS.crCoC->H.CS.crCoC(cap/cast)@E-E-E-E8w //TelephonyConnectionService创建完成
M0E743D  09-18 09:50:09.791  1765  1765 D TranTele/TranFlashCallController: [FlashCallHandler][onCallStateChanged] Call state: ALERTING //监听到call状态变为alerting
M0E743E  09-18 09:50:09.792  1765  1765 I TranTele/TranFlashCallController: [FlashCallHandler][checkFlashCall] is flash call: TC@36_1, connectionExtras:Bundle[{transsion.telephony.extra.FLASH_CALL=Success}] //设置flash call为成功
S0E77D6  09-18 09:50:10.894  1230  8583 I Telecom : Event: RecordEntry TC@36: SET_DISCONNECTED, disconnected set explicitly> DisconnectCause [ Code: (LOCAL) Label: () Description: () Reason: (LOCAL) Tone: (27)  TelephonyCause: 3/-1 ImsReasonInfo: null]: CSW.sDc(cap)@FAM //通话结束，打印挂断原因(flash call正常会自动挂断，TelephonyCause为非异常)
M0E77DE  09-18 09:50:10.897  4785  4785 I Dialer  : FlashCall - isFlashCall  , oldState = 6, state = 10, flashCallText = Flash_Call_Success //dialer读取到通话结果为成功
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
