---
name: com-data-datasetupfail
description: "「数据连接建立失败」COMMON；data call失败、没有发起data call、数据业务无法上网、数据断连。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# COM_DATA_DataSetupFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 数据连接建立失败
- **特征**: data call失败、没有发起data call、数据业务无法上网、数据断连
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

- **发起data call**: `SETUP_DATA_CALL`
- **DNC判断是否需要发起data call**: `DNC.*Data evaluation.*evaluation reason`
- **当前的网络注册信息**: `RILJ.*<.*DATA_REGISTRATION_STATE.*RegStateResult`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
07-22 16:53:53.714  1576  2525 D RILJ    : [3597]> DATA_REGISTRATION_STATE [PHONE0]
07-22 16:53:53.715   758   787 D RIL     : onRequest: DATA_REGISTRATION_STATE radioState = RADIO_ON
07-22 16:53:53.718  1576  1591 D RILJ    : [3597]< DATA_REGISTRATION_STATE RegStateResult{regState: REG_HOME, rat: LTE, reasonForDenial: -1, cellIdentity: CellIdentity.lte(CellIdentityLte{mcc: 460, mnc: 00, ci: 220188609, pci: 310, tac: 13074, earfcn: 38950, operatorNames: OperatorInfo{alphaLong: 中国移动, alphaShort: CMCC, operatorNumeric: , status: 0}, bandwidth: 20000, additionalPlmns: [], csgInfo: null, bands: [BAND_40]}), registeredPlmn: 46000, accessTechnologySpecificInfo: AccessTechnologySpecificInfo.eutranInfo(EutranRegistrationInfo{lteVopsInfo: LteVopsInfo{isVopsSupported: true, isEmcBearerSupported: false}, nrIndicators: NrIndicators{isEndcAvailable: false, isDcNrRestricted: false, isNrAvailable: false}, lteAttachResultType: 0, extraInfo: 0})} [PHONE0] //收到data注册状态的上报
07-22 16:54:00.579  1576  2473 D RILJ    : [3723]> SETUP_DATA_CALL,reason=NORMAL,accessNetworkType=EUTRAN,dataProfile=[DataProfile=[ApnSetting] 3gnet, 2903, 46001, 3gnet, , null, , null, null, 0, supl | hipri | default | xcap, IPV4V6, IPV4V6, true, 0, false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 961, false, UNEDITED, TrafficDescriptor={mDnn=3gnet, null}, preferred=true],allowRoaming=false,linkProperties=null,pduSessionId=0,sliceInfo=null,trafficDescriptor=TrafficDescriptor={mDnn=3gnet, null},matchAllRuleAllowed=true [PHONE1] //发起数据连接建立请求，携带的是APN信息
07-22 16:54:00.580   758   793 D RIL     : onRequest: SETUP_DATA_CALL radioState = RADIO_ON
07-22 16:54:00.618  1576  2282 D RILJ    : [3723]< SETUP_DATA_CALL DataCallResponse: { cause=NONE(0x0) retry=-1 cid=1 linkStatus=2 protocolType=2 ifname=seth_lte8 addresses=[10.181.228.16/32, 2408:8462:2c10:4760:3816:37ff:feb5:2210/64] dnses=[/221.7.92.100, /221.5.203.100, /2408:8663::1, /2408:8662::1] gateways=[/0.0.0.0, /::] pcscf=[] mtu=0 mtuV4=0 mtuV6=0 handoverFailureMode=legacy pduSessionId=0 defaultQos=null qosBearerSessions=[] sliceInfo=SliceInfo{mSliceServiceType=NONE, mSliceDifferentiator=0, mMappedHplmnSliceServiceType=NONE, mMappedHplmnSliceDifferentiator=0, mStatus=UNKNOWN} trafficDescriptors=[TrafficDescriptor={mDnn=3gnet, null}] networkValidationStatus=unsupported} [PHONE1] //返回数据连接建立结果，如果cause不为其他值表示建立成功
07-22 16:54:00.427  1576  1576 D DNC-1   : Data evaluation: evaluation reason:NEW_REQUEST, Data allowed reason: NORMAL, candidate profile=[DataProfile=[ApnSetting] 3gnet, 2903, 46001, 3gnet, , null, , null, null, 0, supl | hipri | default | xcap, IPV4V6, IPV4V6, true, 0, false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 961, false, UNEDITED, TrafficDescriptor={mDnn=3gnet, null}, preferred=true], time=16:54:00.416, network type=LTE, reg state=HOME, [NetworkRequest [ REQUEST id=1, [ Capabilities: INTERNET&NOT_RESTRICTED&TRUSTED&NOT_VPN&NOT_VCN_MANAGED&NOT_BANDWIDTH_CONSTRAINED RequestorUid: 1000 RequestorPkg: android UnderlyingNetworks: Null] ], mPriority=20, state=UNSATISFIED, mAttachedDataNetwork=null, isMetered=true, created time=16:54:00.408, evaluation result=Data evaluation: evaluation reason:NEW_REQUEST, Data allowed reason: NORMAL, candidate profile=[DataProfile=[ApnSetting] 3gnet, 2903, 46001, 3gnet, , null, , null, null, 0, supl | hipri | default | xcap, IPV4V6, IPV4V6, true, 0, false, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 961, false, UNEDITED, TrafficDescriptor={mDnn=3gnet, null}, preferred=true], time=16:54:00.416]
07-28 15:06:00.806806  2619 10097 I MobileConnectionRepository_MtkImsConnectionStateListener: subId=6, updateIms: mImsRadioTech=0, mImsCap=0,isDisableWfc=false, isInService=true, isImsOverWfc=false, isImsOverVoice=true //System UI打印收到的状态，根据状态值在状态栏显示icon
07-28 15:00:38.865613  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: updateSpnDisplay: changed sending intent, rule=2, showPlmn='true', plmn='Emergency calls only', showSpn='false', spn='null', dataSpn='', subId='6'
07-28 15:00:39.263929  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: radio is on but out of service, set plmn='Emergency calls only'
07-28 15:00:39.264088  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rawSpn = 
07-28 15:00:39.264200  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rule = 2
07-28 15:00:39.264947  2830  2830 D MTKSST  : [GsmSST0] TDD updateSpnDisplay mSS.getOperatorNumeric() = 
07-28 15:00:39.642638  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: radio is on but out of service, set plmn='Emergency calls only'
07-28 15:00:39.642714  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rawSpn = 
07-28 15:00:39.642797  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rule = 2
07-28 15:00:39.643507  2830  2830 D MTKSST  : [GsmSST0] TDD updateSpnDisplay mSS.getOperatorNumeric() = 
07-28 15:00:39.647876  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: radio is on but out of service, set plmn='Emergency calls only' //脱网，设置plmn为"Emergency calls only"
07-28 15:00:39.647936  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rawSpn = 
07-28 15:00:39.647996  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rule = 2
07-28 15:00:39.648403  2830  2830 D MTKSST  : [GsmSST0] TDD updateSpnDisplay mSS.getOperatorNumeric() = 
07-28 15:00:39.752464  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rawPlmn = SMART
07-28 15:00:39.752516  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rawSpn = 
07-28 15:00:39.752570  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: rule = 2
07-28 15:00:39.753028  2830  2830 D MTKSST  : [GsmSST0] TDD updateSpnDisplay mSS.getOperatorNumeric() = 51503
07-28 15:00:39.755136  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: updateSpnDisplay: changed sending intent, rule=2, showPlmn='true', plmn='SMART', showSpn='false', spn='SMART', dataSpn='', subId='6' //驻网完毕，设置为显示plmn，不显示spn，plmn为SMART
07-28 15:00:40.073686  2830  2830 D MTKSST  : [GsmSST0] updateSpnDisplay: r

…(已截断，完整内容见源 JSON 对应记录的 normal_log)…
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
