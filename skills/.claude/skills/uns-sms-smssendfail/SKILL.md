---
name: uns-sms-smssendfail
description: "「发送短信失败」UNISOC。拉 main/system/radio 对 patterns 出结论。"
---

# UNS_SMS_SmsSendFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 发送短信失败
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

- **发送短信给订阅者**: `SmsController.*sendTextForSubscriber caller`
- **获取短消息中心地址**: `RIL.*GET_SMSC_ADDRESS`
- **发送短信**: `SMSDispatcher.*sendText id`
- **配置STK短信发送支持**: `SMSDispatcher.*config_stk_sms_send_support`
- **GSM短信分发器发送短信**: `GsmSMSDispatcher.*sendSms:`
- **RIL层发送短信**: `RIL.*SEND_SMS`
- **短信/彩信分析插槽信息类型**: `SmsMmsAnalytics.*SlotInfo.*Type`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
R011098  09-22 10:42:40.378  2410 10833 D SmsController: sendTextForSubscriber caller=com.google.android.apps.messaging //SmsController收到MO SMS调用，短信应用是google message
R0110AA  09-22 10:42:40.392  2410 10833 D RILJ    : [1036]> GET_SMSC_ADDRESS [PHONE0] //RILJ获取SMSC的地址
R0110AE  09-22 10:42:40.393   750   772 D RIL     : onRequest: GET_SMSC_ADDRESS radioState = RADIO_ON //RILD收到SMSC获取请求
R0110B8  09-22 10:42:40.396  2410  3423 D RILJ    : [1036]< GET_SMSC_ADDRESS +316540942000 [PHONE0] //RILJ收到SMSC响应结果
R0110BE  09-22 10:42:40.397  2410 10833 D SMSDispatcher: sendText id: {x-message-id:-7893678183362499398} //SMSDispatcher准备发送短信
R0110BF  09-22 10:42:40.397  2410 10833 I SMSDispatcher: bool.config_stk_sms_send_support= false //判断不支持STK SMS
R0110CA  09-22 10:42:40.420  2410 10833 D GsmSMSDispatcher: sendSms:  isIms()=true mRetryCount=0 mImsRetry=0 mMessageRef=0 mUsesImsServiceForIms=false SS=0 {x-message-id:-7893678183362499398} //子类GsmSMSDispatcher开始发送短信
R0110CD  09-22 10:42:40.423  2410 10833 D RILJ    : [1037]> IMS_SEND_SMS [PHONE0] //RILJ向RILD请求发送短信，并且是通过IMS去发送
R0110D2  09-22 10:42:40.426   750   770 D RIL     : onRequest: IMS_SEND_SMS radioState = RADIO_ON //RILD收到通过IMS发送SMS的请求
R0111EB  09-22 10:42:40.754  2410  3423 D RILJ    : [1037]< IMS_SEND_SMS { mMessageRef = 1, mErrorCode = 0, mAckPdu = , {x-message-id:-7893678183362499398}} [PHONE0] //RILJ收到发送SMS的响应
R0111F6  09-22 10:42:40.767  2410  2410 D SmsMmsAnalytics: SlotInfo = 0 Type = SMS Outgoing Status = SuccessRAT LTE 13Failure Reason = NA //SmsMmsAnalytics总结当前SMS相关信息。
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
