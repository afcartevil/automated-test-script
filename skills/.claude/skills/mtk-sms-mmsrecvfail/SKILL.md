---
name: mtk-sms-mmsrecvfail
description: "「接收彩信失败」MTK。拉 main/system/radio 对 patterns 出结论。"
---

# MTK_SMS_MmsRecvFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 接收彩信失败
- **特征**: 
- **平台边界**: 与 **MTK** 机型或 Jira 芯片字段一致时使用。
- **补充**: 无法收到彩信或者下载彩信的过程中出现异常

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

- **RILD收到modem上报的短信的AT命令**: `AT.*CMT`
- **RILD检查是否为彩信**: `SuplMsgDispatcher.*wap push`
- **SmsMessage处理MMS的信息**: `SmsMessage.*wap.*mms`
- **RILJ收到RILD上报的MT SMS**: `RILJ.*UNSOL_RESPONSE_NEW_SMS`
- **RILD判断当前的SMS类型**: `RmcGsmSmsBase.*current sms_type`
- **RILJ处理MT MMS**: `WAP_PUSH`
- **拉起MmsService**: `MmsService.*onCreate`
- **根据SIM卡的mccmnc去获取配置**: `MmsService.*MmsConfigManager loads mms config for`
- **通过MmsNetworkManager创建MMS能力的网络请求**: `MmsService.*DownloadRequest.*start new network request`
- **通过AT建立MMS类型网络链路**: `AT.*EAPNACT.*mms`
- **通过网络下载mms的过程**: `MmsService.*DownloadRequest.*HTTP:`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
09-23 09:47:16.608401  1686  1696 I AT      : [0] RIL_URC_READER: line1:+CMT:***,line2:*** //RILD收到modem上报的短信的AT命令
09-23 09:47:16.618325  1686  1780 D SuplMsgDispatcher: dispatchSuplMsg not sms, check wap push! //RILD检查不是SMS类型，准备检查是否MMS
09-23 09:47:16.618347  1686  1780 D SuplMsgDispatcher: dispatchSuplMsg is wap push message! //确认是MMS类型
09-23 09:47:16.618552  1686  1780 D SmsMessage: parsePdu mWapAppId: 4, mContentType: application/vnd.wap.mms-message //SmsMessage处理MMS的信息
09-23 09:47:16.619957  2545  2764 D RILJ    : [UNSL]< UNSOL_RESPONSE_NEW_SMS [PHONE0] //RILJ收到RILD上报的MT SMS
09-23 09:47:16.663774  1686  1712 D RmcGsmSmsBase: [0] current sms_type = SMS_INBOUND_3GPP_CMT //RILD判断当前的SMS类型
09-23 09:47:16.697104  2545  2545 D Mtk_WAP_PUSH: put sc addr info into intent 2 //RILJ处理MT MMS
09-23 09:47:17.353279  2545  2545 D MtkGsmInboundSmsHandler-0: Ordered broadcast completed for android.provider.Telephony.WAP_PUSH_DELIVER in: 635 ms //处理MMS广播
09-23 09:47:17.358779  2545  2545 D MtkGsmInboundSmsHandler-0: Ordered broadcast completed for android.provider.Telephony.WAP_PUSH_RECEIVED in: 3 ms //处理MMS广播
09-23 09:47:17.415786  2545  2545 D MmsService: onCreate //拉起MmsService
09-23 09:47:17.418918  2545  2545 I MmsService: MmsConfigManager loads mms config for 460/00, CarrierId 1435 //根据SIM卡的mccmnc去获取配置
09-23 09:47:17.484987  2545 13013 D MmsService: [DownloadRequest@53451d0 {x-message-id:4192594475027988220} subId: 2 currentState: "Created" result: 0] MmsNetworkManager: start new network request //通过MmsNetworkManager创建MMS能力的网络请求，建立对应的网络链路
09-23 09:47:17.589344  1686  1714 I AT      : [0] AT> AT+EAPNACT=1,"cmwap","mms",0,,"dnn=cmwap",,0 (RIL_CMD_READER_4 tid:476353551536) //RILD通过AT命令，建立MMS类型网络链路
09-23 09:47:17.898388  2545 13013 D MmsService: [DownloadRequest@53451d0 {x-message-id:4192594475027988220} subId: 2 currentState: "DoingHttp" result: 1] HTTP: GET http://120.198.247.46[32], proxy=10.0.0.172:80, PDU size=0 //网络建立成功后，MmsService发送get请求下载MMS
09-23 09:47:19.346123  2545 13013 D MmsService: [DownloadRequest@53451d0 {x-message-id:4192594475027988220} subId: 2 currentState: "DoingHttp" result: 1] HTTP: 200 ok //网络响应200，下载成功
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
