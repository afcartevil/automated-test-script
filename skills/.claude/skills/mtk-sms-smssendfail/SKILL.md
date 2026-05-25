---
name: mtk-sms-smssendfail
description: "「发送短信失败」MTK。拉 main/system/radio 对 patterns 出结论。"
---

# MTK_SMS_SmsSendFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 发送短信失败
- **特征**: 
- **平台边界**: 与 **MTK** 机型或 Jira 芯片字段一致时使用。
- **补充**: 发送短信这个操作失败或者未完成

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

- **SmsController被调用发短信接口**: `SmsController.*sendTextForSubscriber.*caller`
- **获取SMSC的地址**: `RILJ.*GET_SMSC_ADDRESS`
- **调用SMSDispatcher的发短信接口**: `SMSDispatcher.*sendText`
- **stk的sms配置**: `SMSDispatcher.*config_stk_sms_send_support`
- **短信的编码格式**: `SMS.*is3GPP2Format`
- **当前的call状态**: `sms.*inCall.*imsCall`
- **RILJ发送SMS请求到RILD**: `RIL.*SEND_SMS`
- **MO_SMS的AT**: `AT.*(\+CMGS)`
- **响应AT**: `AT.*(\+CMS)`
- **phone进程处理响应结果**: `SmsImpl.*sendSmsRsp`
- **SMSDispatcher回调接口被调用**: `SMSDispatcher.*onSendSmsResult`
- **SmsMmsAnalytics打印sms相关信息**: `SmsMmsAnalytics.*SlotInfo`
- **fwk收到SMS的响应结果**: `MtkImsSmsImpl.*sendSmsRsp `
- **RIL的SMS流程**: `RIL_REQUEST_IMS_SEND_SMS_EX`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
09-08 13:54:28.611428  3667  3699 D SmsController: sendTextForSubscriber caller=com.google.android.apps.messaging //phone进程收到了MO SMS的请求，短信应用是google message
09-08 13:54:28.626347  3667  3699 D RILJ    : [1404]> GET_SMSC_ADDRESS [PHONE0] //RILJ向RILD请求SMSC的地址
09-08 13:54:28.632947  3667  4085 D RILJ    : [1404]< GET_SMSC_ADDRESS +316540942000 [PHONE0] //RILJ收到RILD返回的SMSC地址
09-08 13:54:28.633480  3667  3699 D SMSDispatcher: sendText id: {x-message-id:-235120830395027738} //SMSDispatcher是父类，调用了sendText方法
09-08 13:54:28.634041  3667  3699 I SMSDispatcher: bool.config_stk_sms_send_support= false //判断不支持stk mo sms 
09-08 13:54:28.635182  3678  4290 D MtkImsSmsImpl: [0] mPhoneId:0,is3GPP2Format:false,format: //判断当前的SMS编码格式是否使用3GPP2协议
09-08 13:54:28.649156  3667  3699 D ImsSmsDispatcher [0]: sendSms:  mRetryCount=0 mMessageRef=0 SS=0 //子类ImsSmsDispatcher开始发送短信，当前重试次数是0，SS=0表示当前有服务，1表示无服务，2表示紧急服务，3表示radio off
09-08 13:54:28.669183  1865  1870 D RtcImsSmsCtrl: [0] inCall = 0, imsCall = 0, cdmaRat = 0 //流程走到RILD，当前没有cs和ps 上的通话在进行
09-08 13:54:28.670882  1865  1897 I AT      : [0] AT> AT+CMGS=*** (RIL_CMD_NRT_8, tid:519297895600) //RILD通过AT命令，将MO SMS操作发到modem
09-08 13:54:29.001055  1865  1896 I AT      : [0] AT< +CMGS: 216 (RIL_CMD_NRT_8, tid:519298960560) //RILD收到modem响应的AT
09-08 13:54:29.003102  3678  3678 D MtkImsSmsImpl: [0] sendSmsRsp toke=1,messageRef=216,status=1,reason=0 //Phone进程处理SMS响应结果
09-08 13:54:29.003606  3667  4036 D ImsSmsDispatcher [0]: onSendSmsResult token=1 messageRef=216 status=1 reason=0 networkReasonCode=-1 //ImsSmsDispatcher处理MO SMS响应结果
09-08 13:54:29.032721  3667  4036 D SmsMmsAnalytics: Is Over Ims = true sendErrorCode = 0SlotInfo =0 //SmsMmsAnalytics确认MO SMS是通过IMS发送的，且发送成功
09-08 13:54:29.033389  3667  4036 D SmsMmsAnalytics: SlotInfo = 0 Type = SMS Outgoing Status = SuccessRAT UNKNOWN 0Failure Reason = NA //确认发送的类型是SMS
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
