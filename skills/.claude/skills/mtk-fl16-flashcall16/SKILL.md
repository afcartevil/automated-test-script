---
name: mtk-fl16-flashcall16
description: "「FLASH_CALL_16」MTK；FLASH_CALL失败、FLASH_CALL异常。拉 main/system/radio 对 patterns 出结论。"
---

# MTK_FL16_FlashCall16

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: FLASH_CALL_16
- **特征**: FLASH_CALL失败、FLASH_CALL异常
- **平台边界**: 与 **MTK** 机型或 Jira 芯片字段一致时使用。

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

- **Telecom层确认Call建立/创建**: `Telecom.*Event.*CREATED`
- **Telecom层Call状态流转(如CONNECTING->DIALING, RINGING->DISCONNECTED)**: `Telecom.*setCallState`
- **Telecom层断开连接及原因(包含本地挂断或对端/未接挂断原因)**: `Telecom.*SET_DISCONNECTED`
- **FlashCall核心控制逻辑(含每日次数检查、自动挂断逻辑、大数据埋点及通话释放)**: `TranFlashCallController`
- **IMS层Flash消息处理(含消息加解密、收发ACK确认信号)**: `ImsFlashMessageUtils`
- **[MO] Dialer获取今日剩余Flash Call次数**: `Dialer.*getFlashCallRemainderTimes`
- **[MO] Dialer获取用户当前选择发送的Flash消息内容**: `Dialer.*getFlashMessageJson`
- **[MO] Dialer获取Flash Call最终状态及结果(是否成功/有无异常)**: `Dialer.*flashCallText`
- **[MT] Dialer在未接来电通知中解析并显示Flash消息内容**: `Dialer.*MissedCallNotifier.*Flash_Call`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
MO:
03-04 14:58:53.480932  2769  2789 I TranFlashCallController: getFlashMsgTimes mTotalFlashCallTimes: 20 mUsedFlashCallTimes: 17 //每日使用flashCall上限(20),以及今日已使用的次数(17)
03-04 14:58:53.481247  6558  6558 I Dialer  : getFlashCallRemainderTimes - getFlashCallRemainderTimes : 3 //今日剩余flash call此时(3)
03-04 14:58:55.017343  6558  6558 I Dialer  : getFlashMessageJson - flashMessage :: {"fcmsg":"0|Happy holidays","extra":"Flash_Call"} //用户选择message(Happy holidays)
03-04 14:58:55.030037  1766  1787 I Telecom : Event: RecordEntry TC@4: CREATED, com.sh.smart.caller;requestedAcct:none, selfMgd:false: TSI.pC(cssc)@AZ0 //Telecom确认call建立
03-04 14:58:55.207826  2713  2817 I ImsFlashMessageUtils: getInfoFromSubject callSubject : {"fcmsg":"0|Happy holidays","extra":"Flash_Call"} //tele侧获取到message内容(Happy holidays)
03-04 14:58:55.208050  2713  2817 I ImsFlashMessageUtils: setImsFlashCallInfo flashCallInfo: <https://flash_call>;purpose=icon;call-reason="6zFvLdH35rV31CtAM6iyML" //tele侧将message内容加密
03-04 14:58:55.270486  1766  4325 I Telecom-CallsManager: setCallState CONNECTING -> DIALING, call: [Call id=TC@4, state=CONNECTING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 6, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 6, UserHandle{0}, handle=tel:**********, vidst=A, childs(0), has_parent(false), mtkcap=[ sup_hld mut !v2a], mtkprop=[ m_volte], cap=[ sup_hld mut !v2a], prop=[]], voip=false: (...->CS.crCo->H.CS.crCo->H.CS.crCo.pICR)->CSW.hCCC(cap/cast)@E-E-AaM //call状态变为dialing
03-04 14:58:55.271571  6558  6558 I Dialer  : FlashCall - isFlashCall  , oldState = 13, state = 6, flashCallText = , flashCallError = //Dialer获取到call状态变化，并拿取当前flashCallText(代表flashcall是否成功)和flashCallError(message发送是否有异常)，目前为空
03-04 14:58:55.278003  2769  2769 I TranFlashCallController: [onStateChanged] callId: TC@4, state: 1 //call状态变化
03-04 14:58:56.835634  2713  2713 I ImsFlashMessageUtils: setImsFlashCallInfo reason : flash_call_ack, flashCallInfo : <https://flash_call_ack>;purpose=icon //IMS模块收到对端反馈flash_call_ack，表示已收到message
03-04 14:58:56.836072  2713  2713 I ImsFlashMessageUtils: setImsFlashCallInfo callExtras : {"fcack":"fcack"} //IMS模块将“对端已收到message”的情况打包成消息发送给其他模块
03-04 14:58:56.869041  2769  2992 I TranFlashCallController: [checkFlashCallWhenAlerting]flash call alerting, start hanging up //收到对端响铃消息，执行延迟挂断
03-04 14:58:56.869753  2769  2992 I TranFlashCallController: [setSubjectInfo] callExtras = {"fcmsg":"0|Happy holidays","extra":"Flash_Call","fcstate":"Success","fcerror":1} //发送当前flash call状态，"fcstate":"Success"表示call已呼通，"fcerror":1表示暂未收到“对端已收到message”的消息
03-04 14:58:58.072123  2769  3036 I TranFlashCallController: [handleMessage] hang up flash call //执行挂断此通话
03-04 14:58:58.073181  2769  3036 I TranFlashCallController: [setSubjectInfo] callExtras = {"fcmsg":"0|Happy holidays","extra":"Flash_Call","fcstate":"Success","fcerror":0} //收到IMS模块发送的“对端已收到message”的消息，修改"fcerror"为0，表示message已发送成功
03-04 14:58:58.076480  2769  3036 I TranFlashCallController: uploadTrancareLog serverLogBundle[{fc_ringing=true, fc_intent=10, cellid=2573573, fc_dur=8000, fc_ver=1.0, fc_forwarded=false, pci=496, rat=LTE, tac=100, band=3, arfcn=1250, hplmn=63911, rplmn=63910, fc_call_time=2}] //大数据记录用户使用flash call的次数
03-04 14:58:58.087599  2769  2769 I TranFlashCallController: [onStateChanged] callId: TC@4, state: 10 //call状态变化
03-04 14:58:58.088011  6558  6558 I Dialer  : FlashCall - isFlashCall  , oldState = 6, state = 9, flashCallText = Success, flashCallError = 0 //Dialer获取到call状态变化，并拿取当前flashCallText和flashCallError
03-04 14:58:58.227010  2769  2769 I TranFlashCallController: [onStateChanged] callId: TC@4, state: 7 //call状态变化
03-04 14:58:58.223048  1766  2926 I Telecom-CallsManager: setCallState DISCONNECTING -> DISCONNECTED, call: [Call id=TC@4, state=DISCONNECTING, tpac=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 6, UserHandle{0}, cmgr=ComponentInfo{com.android.phone/com.android.services.telephony.TelephonyConnectionService}, 6, UserHandle{0}, handle=tel:**********, vidst=A, childs(0), has_parent(false), mtkcap=[ sup_hld mut], mtkprop=[ m_volte], cap=[ sup_hld mut], prop=[]], voip=false: CSW.sDc(cap)@AcA //call状态变为DISCONNECTED
03-04 14:58:58.223195  1766  2926 I Telecom : Event: RecordEntry TC@4: SET_DISCONNECTED, disconnected set explicitly> DisconnectCause [ Code: (LOCAL) Label: () Description: () Reason: (LOCAL) Tone: (27)  TelephonyCause: 3/-1 ImsReasonInfo: ImsReasonInfo :: {504 : CODE_USER_DECLINE, 0, null}]: CSW.sDc(cap)@AcA //打印挂断原因：本地挂断
03-04 14:58:58.224949  6558  6558 I Dialer  : FlashCall - isFlashCall  , oldState = 9, state = 10, flashCallText = Success, flashCallError = 0 //Dialer获取到call状态变化，并拿取当前flashCallText和flashCallError，call状态变为10，表示call已结束，最后拿到的状态反馈给用户（flashCallText = Success, flashCallError = 0表示，call成功呼通，message发送无异常，成功）
03-04 14:58:58.227871  2769  2769 I TranFlashCallController: [removeCall] getIntentExtrasIntentExtra:[EXTRA_CALL_SUBJECT:{"fcmsg":"0|Happy holidays","extra":"Flash_Call"},FLASH_CALL_RESULT_EXTRA:null //TranFlashCallController释放此通话，并打印message内容
03-04 14:58:58.227939  2769  2769 I TranFlashCallController: [removeCall] getExtras Extras:[EXTRA_CALL_SUBJECT:{"fcack":"fcack"},FLASH_CALL_RESULT_EXTRA:{"fcmsg":"0|Happy holidays","extra":"Flash_Call","fcstate":"Success","fcerror":0} //TranFlashCallController释放此通话,并打印最终状态


MT:
03-04 14:58:56.444558  2847  2847 I ImsFlashMessageUtils: setImsFlashCallInfo reason : flash_call, flashCallInfo : 6zFvLdH35rV31CtAM6iyML //ImsFlashMessageUtils获取到对端发送的加密消息
03-04 14:58:56.444848  2847  2847 I ImsFlashMessageUtils: setImsFlashCallAckInfo flashCallAckInfo: <https://flash_call_ack>;purpose=icon //反馈flash_call_ack到对端，表示消息接受成功
03-04 14:58:56.447216  2847  2847 I ImsFlashMessageUtils: setImsFlashCallInfo callExtras : {"extra":"Flash_Call","fcmsg":"0|Happy holidays"} //消息解密(Flash_Call)
03-04 14:58:56.958551  2046  3019 I Telec

…(已截断，完整内容见源 JSON 对应记录的 normal_log)…
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
