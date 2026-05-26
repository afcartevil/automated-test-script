---
name: uns-sms-mmssendfail
description: "「发送彩信失败」UNISOC。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# UNS_SMS_MmsSendFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 发送彩信失败
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

- **MMS服务创建**: `MmsService.*onCreate`
- **MMS发送请求的网络管理器**: `MmsService.*SendRequest.*MmsNetworkManager`
- **MMS发送请求的APN配置**: `MmsService.*SendRequest.*APN`
- **电话网络工厂收到MMS网络请求**: `TelephonyNetworkFactory.*got request NetworkRequest.*mms`
- **电话网络工厂需要MMS网络**: `TelephonyNetworkFactory.*onNeedNetworkFor.*mms`
- **数据网络控制器添加MMS网络请求**: `DNC.*onAddNetworkRequest.*MMS`
- **数据配置文件管理器满足MMS配置文件**: `DPM.*Satisfied profile.*mms`
- **数据网络控制器数据评估原因MMS**: `DNC.*Data evaluation.*evaluation reason.*MMS`
- **数据网络控制器在MMS上创建数据网络**: `DNC.*Creating data network on.*MMS`
- **数据网络控制器连接状态设置MMS数据**: `DNC.*ConnectingState.*setupData.*MMS`
- **RIL层设置MMS数据呼叫**: `RILJ.*SETUP_DATA_CALL.*MMS`
- **RIL层设置数据呼叫响应**: `RILJ.*SETUP_DATA_CALL.*DataCallResponse`
- **RMC数据通用请求设置MMS数据呼叫**: `RmcDcCommon.*requestSetupDataCall.*MMS`
- **AT命令激活MMS APN**: `AT.*EAPNACT.*MMS`
- **MMS服务发送请求HTTP**: `MmsService.*SendRequest.*HTTP:`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
R0155BE  09-22 10:44:11.737  2410 10833 D MmsService: sendMessage {x-message-id:2832259991516647707} //MmsService收到发送message的调用
R0155D3  09-22 10:44:11.763  2410 20193 D MmsService: [SendRequest@e337249 {x-message-id:2832259991516647707} subId: 1 currentState: "Created" result: 0] MmsNetworkManager: start new network request //通过MmsNetworkManager创建MMS的网络链路，用于发送mms
R015636  09-22 10:44:11.862  2410  3427 D RILJ    : [1059]> SETUP_DATA_CALL,reason=NORMAL,accessNetworkType=EUTRAN,dataProfile=[DataProfile=[ApnSetting] CTWAP, 2932, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, TrafficDescriptor={mDnn=ctwap, null}, preferred=false],allowRoaming=false,linkProperties=null,pduSessionId=0,sliceInfo=null,trafficDescriptor=TrafficDescriptor={mDnn=ctwap, null},matchAllRuleAllowed=true [PHONE0] //RILJ向RILD发起建立MMS数据链路的请求
R015700  09-22 10:44:12.125  2410  2426 D RILJ    : [1059]< SETUP_DATA_CALL DataCallResponse: { cause=NONE(0x0) retry=-1 cid=2 linkStatus=2 protocolType=0 ifname=seth_lte1 addresses=[10.19.98.233/32] dnses=[/61.128.192.68] gateways=[/0.0.0.0] pcscf=[] mtu=0 mtuV4=0 mtuV6=0 handoverFailureMode=legacy pduSessionId=0 defaultQos=null qosBearerSessions=[] sliceInfo=SliceInfo{mSliceServiceType=NONE, mSliceDifferentiator=0, mMappedHplmnSliceServiceType=NONE, mMappedHplmnSliceDifferentiator=0, mStatus=UNKNOWN} trafficDescriptors=[TrafficDescriptor={mDnn=ctwap, null}] networkValidationStatus=unsupported} [PHONE0] //RILD响应RILJ的数据建立请求结果
R015711  09-22 10:44:12.137  2410 10833 D MmsService: onPreciseDataConnectionStateChanged:  state: CONNECTED, transport: WWAN, id: 2, netId: 104, network type: LTE, APN Setting: [ApnSetting] CTWAP, 2932, 46011, ctwap, , http://mmsc.vnet.mobi, 10.0.0.200, 80, null, 3, mms, IPV4V6, IP, true, 0, false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 911625348, false, UNEDITED, link properties: {InterfaceName: seth_lte1 LinkAddresses: [ 10.19.98.233/32 ] DnsAddresses: [ /61.128.192.68 ] Domains: null MTU: 1500 TcpBufferSizes: 2097152,6291456,16777216,512000,2097152,8388608 Routes: [ 0.0.0.0/0 -> 0.0.0.0 seth_lte1 mtu 1500 ]}, default QoS: null, fail cause: NONE(0x0), network validation status: unsupported //MmsService收到MMS网络的连接状态通知
R015751  09-22 10:44:12.194  2410 20193 D MmsService: [SendRequest@e337249 {x-message-id:2832259991516647707} subId: 1 currentState: "DoingHttp" result: 1] HTTP: POST http://mmsc.vnet.mobi[21], proxy=10.0.0.200:80, PDU size=265370 //通过post方式去发送MMS
R015752  09-22 10:44:12.195  2410 20193 I MmsService: [SendRequest@e337249 {x-message-id:2832259991516647707} subId: 1 currentState: "DoingHttp" result: 1] HTTP: User-Agent=Android-Mms/2.0
R015753  09-22 10:44:12.195  2410 20193 I MmsService: [SendRequest@e337249 {x-message-id:2832259991516647707} subId: 1 currentState: "DoingHttp" result: 1] HTTP: UaProfUrl=http://www.unisoc.com/wap/SP9832E_UAProfile.xml, UaProfUrlTagName=x-wap-profile
R015778  09-22 10:44:12.517  2410 20193 D MmsService: [SendRequest@e337249 {x-message-id:2832259991516647707} subId: 1 currentState: "DoingHttp" result: 1] HTTP: 200 OK //网络响应200，说明MMS发送成功
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
