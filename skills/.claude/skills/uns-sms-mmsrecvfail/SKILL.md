---
name: uns-sms-mmsrecvfail
description: "「接收彩信失败」UNISOC。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# UNS_SMS_MmsRecvFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 接收彩信失败
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

- **AT命令收到新短信通知**: `AT.*(\+CMT)`
- **RIL层收到新短信未请求响应**: `RILJ.*UNSOL_RESPONSE_NEW_SMS`
- **短信消息体内容**: `SmsMessage.*message.*mMessageBody`
- **WAP推送处理消息**: ` WAP PUSH:.*processMsg`
- **MMS服务创建**: `MmsService: onCreate`
- **MMS服务创建**: `MmsService.*onCreate`
- **MMS配置管理器加载配置**: `MmsService: MmsConfigManager loads mms config for`
- **MMS网络管理器开始新网络请求**: `MmsService.*MmsNetworkManager: start new network request`
- **RIL层设置MMS数据呼叫**: `RILJ.*SETUP_DATA_CALL.*mms`
- **MMS服务精确数据连接状态改变**: `MmsService.*onPreciseDataConnectionStateChanged:  state:`
- **MMS服务下载请求HTTP**: `MmsService.*DownloadRequest.*HTTP:`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
R0128F8  09-22 10:43:42.881   750  1076 D RIL     : Channel[0] AT< +CMT: ,138 //RILD收到modem上报的AT，表示有MT SMS
R0128FB  09-22 10:43:42.882  2410 10833 D RILJ    : [UNSL]< UNSOL_RESPONSE_NEW_SMS [PHONE0] //RILJ收到RILD上报的MT SMS
R012922  09-22 10:43:42.974  2410  2410 D SmsMessage: SMS message ENCODING_8BIT mMessageBody = null. //SMS编码格式
M012929  09-22 10:43:43.033  2852  2891 D WAP PUSH: wpman processMsg 4:application/vnd.wap.mms-message //判断为彩信
R012A77  09-22 10:43:43.742  2410  2410 D MmsService: onCreate //拉起MmsService
R012A80  09-22 10:43:43.752  2410  2410 I MmsService: MmsConfigManager loads mms config for 460/11, CarrierId 2237 //根据SIM卡的mccmnc加载配置
R012AB5  09-22 10:43:43.817  2410 19757 D MmsService: [DownloadRequest@629202c {x-message-id:-5386079572146961439} subId: 1 currentState: "Created" result: 0] MmsNetworkManager: start new network request //通过MmsNetworkManager创建MMS的网络链路
R012AF6  09-22 10:43:43.910  2410  3427 D RILJ    : [1041]> SETUP_DATA_CALL,reason=NORMAL,accessNetworkType=EUTRAN,dataProfile=[DataProfile=[ApnSetting] CTWAP, 2932, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, TrafficDescriptor={mDnn=ctwap, null}, preferred=false],allowRoaming=false,linkProperties=null,pduSessionId=0,sliceInfo=null,trafficDescriptor=TrafficDescriptor={mDnn=ctwap, null},matchAllRuleAllowed=true [PHONE0] //RILJ发起数据链路建立请求，apn是mms
R012BB3  09-22 10:43:44.136  2410  2727 D MmsService: onPreciseDataConnectionStateChanged:  state: CONNECTED, transport: WWAN, id: 2, netId: 103, network type: LTE, APN Setting: [ApnSetting] CTWAP, 2932, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, link properties: {InterfaceName: seth_lte1 LinkAddresses: [ 10.19.60.86/32 ] DnsAddresses: [ /61.128.192.68 ] Domains: null MTU: 1500 TcpBufferSizes: 2097152,6291456,16777216,512000,2097152,8388608 Routes: [ 0.0.0.0/0 -> 0.0.0.0 seth_lte1 mtu 1500 ]}, default QoS: null, fail cause: NONE(0x0), network validation status: unsupported //MmsService更新彩信链路是连接状态
R012C00  09-22 10:43:44.221  2410 19757 D MmsService: [DownloadRequest@629202c {x-message-id:-5386079572146961439} subId: 1 currentState: "DoingHttp" result: 1] HTTP: GET http://10.234.251.180[35], proxy=10.0.0.200:80, PDU size=0 //发起get请求
R012C01  09-22 10:43:44.223  2410 19757 I MmsService: [DownloadRequest@629202c {x-message-id:-5386079572146961439} subId: 1 currentState: "DoingHttp" result: 1] HTTP: IPv4 provisioned
R012C02  09-22 10:43:44.225  2410 19757 I MmsService: [DownloadRequest@629202c {x-message-id:-5386079572146961439} subId: 1 currentState: "DoingHttp" result: 1] HTTP: User-Agent=Android-Mms/2.0
R012C03  09-22 10:43:44.225  2410 19757 I MmsService: [DownloadRequest@629202c {x-message-id:-5386079572146961439} subId: 1 currentState: "DoingHttp" result: 1] HTTP: UaProfUrl=http://www.unisoc.com/wap/SP9832E_UAProfile.xml, UaProfUrlTagName=x-wap-profile
R012C26  09-22 10:43:44.454  2410 19757 D MmsService: [DownloadRequest@629202c {x-message-id:-5386079572146961439} subId: 1 currentState: "DoingHttp" result: 1] HTTP: 200 OK //网络响应200，表示下载MMS成功
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
