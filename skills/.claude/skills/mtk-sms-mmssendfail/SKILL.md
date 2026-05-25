---
name: mtk-sms-mmssendfail
description: "「发送彩信失败」MTK。拉 main/system/radio 对 patterns 出结论。"
---

# MTK_SMS_MmsSendFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 发送彩信失败
- **特征**: 
- **平台边界**: 与 **MTK** 机型或 Jira 芯片字段一致时使用。
- **补充**: 发送彩信的过程失败或者未完成

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

- **拉起MmsService**: `MmsService.*onCreate`
- **调用MmsNetworkManager来创建带有MMS能力的网络请求**: `MmsService.*SendRequest.*MmsNetworkManager`
- **发起请求过程apn相关打印**: `MmsService.*SendRequest.*APN`
- **网络工厂收到mms能力的网络请求**: `TelephonyNetworkFactory.*got request NetworkRequest.*mms`
- **工厂判断需要建立网络**: `TelephonyNetworkFactory.*onNeedNetworkFor.*mms`
- **DataNetworkController添加这个请求**: `DNC.*onAddNetworkRequest.*MMS`
- **匹配上的apn profile**: `DPM.*Satisfied profile.*mms`
- **评估是否需要建立网络连接**: `DNC.*Data evaluation.*evaluation reason.*MMS`
- **创建mms能力的网络连接**: `DNC.*Creating data network on.*MMS`
- **发起data call**: `DNC.*ConnectingState.*setupData.*MMS`
- **RLJ向RILD发起mms apn的data call**: `RILJ.*SETUP_DATA_CALL.*MMS`
- **data call响应结果**: `RILJ.*SETUP_DATA_CALL.*DataCallResponse`
- **RILD收到data call请求**: `RmcDcCommon.*requestSetupDataCall.*MMS`
- **RILD给modem发送AT来激活mms承载**: `AT.*EAPNACT.*MMS`
- **MmsService通过网络发送mms的过程**: `MmsService.*SendRequest.*HTTP:`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
09-22 10:55:45.815428  2498  2498 D MmsService: onCreate //拉起MmsService
09-22 10:55:45.884495  2498 20092 D MmsService: [SendRequest@1b9fcff {x-message-id:486809522494700645} subId: 1 currentState: "Created" result: 0] MmsNetworkManager: start new network request //拉起MmsService调用MmsNetworkManager来创建带有MMS能力的网络请求
09-22 10:55:45.892171  2498  2498 D TelephonyNetworkFactory[0]: got request NetworkRequest [ REQUEST id=495, [ Transports: CELLULAR|SATELLITE Capabilities: MMS&TRUSTED&NOT_VPN Forbidden: LOCAL_NETWORK Specifier: <TelephonyNetworkSpecifier [mSubId = 1]> Uid: 1001 RequestorUid: 1001 RequestorPkg: com.android.mms.service UnderlyingNetworks: Null] ] //TelephonyNetworkFactory收到网络请求
09-22 10:55:45.893032  2498  2498 D TelephonyNetworkFactory[0]: onNeedNetworkFor [NetworkRequest [ REQUEST id=495, [ Transports: CELLULAR|SATELLITE Capabilities: MMS&TRUSTED&NOT_VPN Forbidden: LOCAL_NETWORK Specifier: <TelephonyNetworkSpecifier [mSubId = 1]> Uid: 1001 RequestorUid: 1001 RequestorPkg: com.android.mms.service UnderlyingNetworks: Null] ], mPriority=70, state=UNSATISFIED, mAttachedDataNetwork=null, isMetered=false, created time=03:55:45.891, evaluation result=null] shouldApply true //判断当前的网络工厂可以处理这个网络请求
09-22 10:55:45.944775  2498  2498 D DNC-0   : onAddNetworkRequest: added [NetworkRequest [ REQUEST id=495, [ Transports: CELLULAR|SATELLITE Capabilities: MMS&TRUSTED&NOT_VPN Forbidden: LOCAL_NETWORK Specifier: <TelephonyNetworkSpecifier [mSubId = 1]> Uid: 1001 RequestorUid: 1001 RequestorPkg: com.android.mms.service UnderlyingNetworks: Null] ], mPriority=70, state=UNSATISFIED, mAttachedDataNetwork=null, isMetered=false, created time=03:55:45.891, evaluation result=null] //DataNetworkController添加这个请求
09-22 10:55:45.945796  2498  2498 V DPM-0   : Satisfied profile: [DataProfile=[ApnSetting] CTWAP, 2716, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, true, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, TrafficDescriptor={mDnn=ctwap, null}, preferred=false], last setup=never //DataProfileManager找到合适的apn profile来创建PDN，用于处理mms请求
09-22 10:55:45.949300  2498  2498 D DNC-0   : Data evaluation: evaluation reason:NEW_REQUEST, Data allowed reason: NORMAL, candidate profile=[DataProfile=[ApnSetting] CTWAP, 2716, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, true, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, TrafficDescriptor={mDnn=ctwap, null}, preferred=false], time=03:55:45.948, network type=LTE, reg state=HOME, [NetworkRequest [ REQUEST id=495, [ Transports: CELLULAR|SATELLITE Capabilities: MMS&TRUSTED&NOT_VPN Forbidden: LOCAL_NETWORK Specifier: <TelephonyNetworkSpecifier [mSubId = 1]> Uid: 1001 RequestorUid: 1001 RequestorPkg: com.android.mms.service UnderlyingNetworks: Null] ], mPriority=70, state=UNSATISFIED, mAttachedDataNetwork=null, isMetered=false, created time=03:55:45.892, evaluation result=Data evaluation: evaluation reason:NEW_REQUEST, Data allowed reason: NORMAL, candidate profile=[DataProfile=[ApnSetting] CTWAP, 2716, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, true, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, TrafficDescriptor={mDnn=ctwap, null}, preferred=false], time=03:55:45.948] //判断是否需要进行数据建立， Data allowed reason: NORMAL表示允许发起data call
09-22 10:55:45.949846  2498  2498 D DNC-0   : Creating data network on WWAN with [DataProfile=[ApnSetting] CTWAP, 2716, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, true, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, TrafficDescriptor={mDnn=ctwap, null}, preferred=false], and attaching 1 network requests to it. //表示正在用匹配到的profile去创建对应的DataNetwork实例
09-22 10:55:45.960632  2498  2498 D DN-103-C: ConnectingState: setupData: accessNetwork=EUTRAN, [DataProfile=[ApnSetting] CTWAP, 2716, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, true, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, TrafficDescriptor={mDnn=ctwap, null}, preferred=false], isModemRoaming=false, allowRoaming=false, PDU session id=0, matchAllRuleAllowed=true //DataNetwork发起data call
09-22 10:55:45.964250  2498  3141 D RILJ    : [1247]> SETUP_DATA_CALL,reason=NORMAL,accessNetworkType=EUTRAN,dataProfile=[DataProfile=[ApnSetting] CTWAP, 2716, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 1001, true, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, TrafficDescriptor={mDnn=ctwap, null}, preferred=false],allowRoaming=false,linkProperties=null,pduSessionId=0,sliceInfo=null,trafficDescriptor=TrafficDescriptor={mDnn=ctwap, null},matchAllRuleAllowed=true [PHONE0] //RILJ向RILD发起data call请求
09-22 10:55:45.966377  1625  1671 I RmcDcCommon: [0][requestSetupDataCall] apn=ctwap,  apnIndex=1, cmdIndex=0, profile=mms, protocol=3 //RILD收到data call请求，这里可以判断apn名字，类型等信息
09-22 10:55:45.966407  1625  1671 I AT      : [0] AT> AT+EAPNACT=1,"ctwap","mms",0,,"dnn=ctwap",,0 (RIL_CMD_READER_4 tid:504155888816) //RILD通过AT命令EAPNACT将请求发送到MODEM
09-22 10:55:46.280726  2498  2665 D RILJ    : [1247]< SETUP_DATA_CALL DataCallResponse: { cause=NONE(0x0) retry=-1 cid=302 linkStatus=2 protocolType=0 ifname=ccmni2 addresses=[10.18.61.196/32] dnses=[] gateways=[/10.18.61.196] pcscf=[] mtu=0 mtuV4=0 mtuV6=0 handoverFailureMode=unknown pduSessionId=0 defaultQos=EpsQos { qosClassId=9 downlink=Bandwidth { maxBitrateKbps=0 guaranteedBitrateKbps=0} uplink=Bandwidth { maxBitrateKbps=0 guaranteedBitrateKbps=0}} qosBearerSessions=[] sliceInfo=null trafficDescriptors=[] networkValidationStatus=unsupported} [PHONE0] //RILJ收到RILD的data call响应
09-22 10:55:46.329007  2498 20092 D MmsService: [SendReq

…(已截断，完整内容见源 JSON 对应记录的 normal_log)…
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
