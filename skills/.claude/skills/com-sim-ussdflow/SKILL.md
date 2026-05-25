---
name: com-sim-ussdflow
description: "「USSD流程异常」COMMON；拨号进入运营商菜单失败、drops USSI、drop volte、USSD返回内容未提示/无响应。拉 main/system/radio 对 patterns 出结论。"
---

# COM_SIM_UssdFlow

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: USSD流程异常
- **特征**: 拨号进入运营商菜单失败、drops USSI、drop volte、USSD返回内容未提示/无响应
- **平台边界**: **跨芯片公共**（RIL/Framework/Java）或未限定芯片且现象符合下列场景/特征时使用。

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

- **USSD下发开始**: `dialInternal: dialing w/ mmi`
- **USSD连接识别,返回null则为USSD/MMI代码，不创建普通通话连接**: `placeOutgoingConnection, phone.dial returned null`
- **RIL下发请求**: `SEND_USSD.*>`
- **RIL处理请求**: `sendUssd: serial`
- **RIL请求完成**: `SEND_USSD.*<`
- **UI初始显示，显示USSD进度对话框**: `displayMMIInitiate: running USSD code`
- **Modem接收网络侧响应**: `onUssdInd: mode`
- **RIL上报通知**: `UNSOL_ON_USSD.*<`
- **USSD内容显示**: `ImsRIL.*\d+\)`
- **框架处理响应**: `handleMessage EVENT_USSD received`
- **USSD模式识别，识别USSD模式类型和匹配的MMI对象**: `ussdMode = .*, found =`
- **状态更新，状态包含PENDING/COMPLETE/CANCELLED/FAILED**: `USSD state =`
- **MMI完成通知,通知UI层MMI操作完成**: `onMMIDone: notifying registrants`
- **UI结果更新,更新UI显示结果或输入对话框**: `displayMMIComplete: state=`
- **如果需要用户输入，则构建输入对话框**: `Constructing input dialog`
- **Activity状态处理**: `onMMIComplete: still pending`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
// [阶段1] 框架层识别USSD
GsmConnection: registerForCallEvents
dialInternal: dialing w/ mmi 'UniGsmMmiCode {State=PENDING action=* sc=XXX...}'
Telephony: placeOutgoingConnection, phone.dial returned null
Telephony: dialed MMI code
Telephony: subId: [SIM卡ID]
// [阶段2] RIL层下发
RILJ: [序列号]> SEND_USSD ussd = [隐藏号码] [PHONE0]
RILC: sendUssd: serial [序列号]
RIL: onRequest: SEND_USSD radioState = RADIO_ON
RILC: sendUssdResponse: serial [序列号]
RILJ: [序列号]< SEND_USSD [PHONE0]
// [阶段3] UI初始显示
MMIDialogActivity: showMMIDialog: mmiCode = UniGsmMmiCode {State=PENDING action=* sc=XXX...}
UssdCustomizedUtils: displayMMIInitiate: running USSD code, displaying intermediate progress.
上报
// [阶段4] Modem接收网络响应
RILC: onUssdInd: mode [模式号]
RILC: RIL_SOCKET_[N] UNSOLICITED: UNSOL_ON_USSD length:[长度]
RILC_AIMS: onImsUssdInd: mode [模式号]
// [阶段5] RIL层上报框架层
RILJ: [UNSL]< UNSOL_ON_USSD [模式号] [PHONE0]
ImsRIL: [UNSL]< RIL_IMS_UNSOL_ON_IMS_USSD [消息摘要]
// [阶段6] 框架层接收并处理
UniGsmCdmaPhone: handleMessage EVENT_USSD received
UniGsmCdmaPhone: ussdMode = [模式号], found = UniGsmMmiCode {State=PENDING action=* sc=XXX...}, ussdMessage = [完整消息内容]
// [阶段7] 打印具体内容
UniGsmCdmaPhone: 1) [菜单选项1]
UniGsmCdmaPhone: 2) [菜单选项2]
UniGsmCdmaPhone: ... [更多选项]
// [阶段8] 调用onUssdFinished处理消息
UniGsmMmiCode: onUssdFinished: ussdMessage=[完整消息内容]
// [阶段9] 状态更新和通知
UniGsmCdmaPhone: USSD state = [状态]
UniGsmCdmaPhone: onMMIDone: notifying registrants: UniGsmMmiCode {State=[状态] action=* sc=XXX...}
// [阶段10] UI更新显示
UssdCustomizedUtils: displayMMIComplete: state=[状态]
UssdCustomizedUtils: displayMMIComplete: using text from [状态] MMI message: '[完整消息内容]'
// [阶段11] 根据状态进行UI处理
// 状态=PENDING
UssdCustomizedUtils: displayMMIComplete: USSD code has requested user input. Constructing input dialog.
MMIDialogActivity: onMMIComplete: mmi=UniGsmMmiCode {State=PENDING...}
MMIDialogActivity: onMMIComplete: still pending.
// 状态=COMPLETE
UssdCustomizedUtils: displayMMIComplete: MMI code has finished running.
MMIDialogActivity: onMMIComplete: Got MMI_COMPLETE, finishing dialog activity...
// [阶段12] 框架层通知完成
CallManager: CallManager: handleMessage (EVENT_MMI_COMPLETE)
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
