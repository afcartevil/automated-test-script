---
name: com-network-signalabnormal
description: "「信号异常」COMMON；无信号、信号差、无法驻网、信号不稳定、蜂窝信号弱、信号格数低、网络质量差、网络异常切换、异常驻留5G、G不稳定、频繁掉网、移动网络丢失、驻网丢失、重启后无法驻网/仅紧急呼叫、网络制式显示异常、无服务、…。拉 main/system/radio 对 patterns 出结论。"
---

# COM_NETWORK_SignalAbnormal

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 信号异常
- **特征**: 无信号、信号差、无法驻网、信号不稳定、蜂窝信号弱、信号格数低、网络质量差、网络异常切换、异常驻留5G、G不稳定、频繁掉网、移动网络丢失、驻网丢失、重启后无法驻网/仅紧急呼叫、网络制式显示异常、无服务、异常驻留4G、VoLTE状态异常
- **平台边界**: **跨芯片公共**（RIL/Framework/Java）或未限定芯片且现象符合下列场景/特征时使用。
- **补充**: 无信号

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

- **语音和数据的注册状态**: `.*combinePsRegistrationStates.*mVoiceRegState.*`
- **data注册状态上报**: `.*< DATA_REGISTRATION_STATE.*`
- **voice注册状态上报**: `.*< VOICE_REGISTRATION_STATE.*`
- **信号强度上报**: `.*< SIGNAL_STRENGTH.*`
- **信号强度变化**: `.*MtkSSCtr.*SignalStrength.*`
- **信号强度变化**: `.*onSignalStrengthsChanged.*rsrp.*`
- **信号强度变化**: `.*registred.*rsrp.*rsrq.*sinr`
- **信号强度变化**: `.*< UNSOL_CELL_INFO_LIST.*mRegistered.*`
- **设置网络制式**: `.*setAllowedNetworkTypes.*`
- **设置网络制式**: `.*> SET_ALLOWED_NETWORK_TYPES_BITMAP.*`
- **设置网络制式**: `.*handleSetAllowedNetworkTypeRequest.*`
- **设置网络制式**: `.*NW_SET_RAT_REQ.*`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
01-04 14:05:48.232  2707  2707 D MTKSST  : [GsmSST1] combinePsRegistrationStates: {mVoiceRegState=3(POWER_OFF), mDataRegState=1(OUT_OF_SERVICE), mChannelNumber=-1, duplexMode()=0, mCellBandwidths=[], mOperatorAlphaLong=, mOperatorAlphaShort=, isManualNetworkSelection=false(automatic), getRilVoiceRadioTechnology=0(Unknown), getRilDataRadioTechnology=0(Unknown), mCssIndicator=unsupported, mNetworkId=-1, mSystemId=-1, mCdmaRoamingIndicator=-1, mCdmaDefaultRoamingIndicator=-1, mIsEmergencyOnly=false, isUsingCarrierAggregation=false, mArfcnRsrpBoost=0, mNetworkRegistrationInfos=[NetworkRegistrationInfo{ domain=CS transportType=WWAN registrationState=UNKNOWN networkRegistrationState=UNKNOWN roamingType=NOT_ROAMING accessNetworkTechnology=UNKNOWN rejectCause=0 emergencyEnabled=false availableServices=[] cellIdentity=null voiceSpecificInfo=null dataSpecificInfo=null nrState=**** rRplmn= isUsingCarrierAggregation=false isNonTerrestrialNetwork=TERRESTRIAL}, NetworkRegistrationInfo{ domain=PS transportType=WWAN registrationState=UNKNOWN networkRegistrationState=UNKNOWN roamingType=NOT_ROAMING accessNetworkTechnology=UNKNOWN rejectCause=0 emergencyEnabled=false availableServices=[] cellIdentity=null voiceSpecificInfo=null dataSpecificInfo=null nrState=**** rRplmn= isUsingCarrierAggregation=false isNonTerrestrialNetwork=TERRESTRIAL}, NetworkRegistrationInfo{ domain=PS transportType=WLAN registrationState=UNKNOWN networkRegistrationState=UNKNOWN roamingType=NOT_ROAMING accessNetworkTechnology=UNKNOWN rejectCause=0 emergencyEnabled=false availableServices=[] cellIdentity=null voiceSpecificInfo=null dataSpecificInfo=null nrState=**** rRplmn= isUsingCarrierAggregation=false isNonTerrestrialNetwork=TERRESTRIAL}], mNrFrequencyRange=0, mOperatorAlphaLongRaw=, mOperatorAlphaShortRaw=, mIsDataRoamingFromRegistration=false, mIsIwlanPreferred=false, mIsUsingNonTerrestrialNetwork=false}
01-04 14:05:55.222  2707  3515 D RILJ    : [0307]< DATA_REGISTRATION_STATE RegStateResult{regState: REG_HOME, rat: LTE, reasonForDenial: NONE, cellIdentity: CellIdentity.lte(CellIdentityLte{mcc: 460, mnc: 11, ci: 85825684, pci: 336, tac: 39424, earfcn: 2452, operatorNames: OperatorInfo{alphaLong: CHN-CT, alphaShort: CT, operatorNumeric: , status: 0}, bandwidth: 10000, additionalPlmns: [], csgInfo: null, bands: [BAND_5]}), registeredPlmn: 46011, accessTechnologySpecificInfo: AccessTechnologySpecificInfo.eutranInfo(EutranRegistrationInfo{lteVopsInfo: LteVopsInfo{isVopsSupported: true, isEmcBearerSupported: true}, nrIndicators: NrIndicators{isEndcAvailable: false, isDcNrRestricted: false, isNrAvailable: false}, lteAttachResultType: 1, extraInfo: 0})} [PHONE0]
01-04 14:05:55.237  2707  3515 D RILJ    : [0308]< VOICE_REGISTRATION_STATE RegStateResult{regState: NOT_REG_MT_NOT_SEARCHING_OP, rat: UNKNOWN, reasonForDenial: 18, cellIdentity: CellIdentity.noinit(false), registeredPlmn: , accessTechnologySpecificInfo: AccessTechnologySpecificInfo.noinit(false)} [PHONE0]
01-04 14:05:40.261  2707  3128 D RilRequest: [0053]< SIGNAL_STRENGTH error: com.android.internal.telephony.CommandException: RADIO_NOT_AVAILABLE ret=SignalStrength:{mAverageLevel=-1mCdma=CellSignalStrengthCdma: cdmaDbm=2147483647 cdmaEcio=2147483647 evdoDbm=2147483647 evdoEcio=2147483647 evdoSnr=2147483647 level=0,mGsm=CellSignalStrengthGsm: rssi=-113 ber=0 mTa=0 mLevel=0,mWcdma=CellSignalStrengthWcdma: ss=-113 ber=0 rscp=-120 ecno=-24 level=0,mTdscdma=CellSignalStrengthTdscdma: rssi=-113 ber=0 rscp=-120 level=0,mLte=CellSignalStrengthLte: rssi=-113 rsrp=2147483647 rsrq=0 rssnr=0 cqiTableIndex=2147483647 cqi=0 ta=0 level=1 parametersUseForLevel=1,mNr=CellSignalStrengthNr:{ csiRsrp = 2147483647 csiRsrq = 2147483647 csiCqiTableIndex = 2147483647 csiCqiReport = [] ssRsrp = 2147483647 ssRsrq = 0 ssSinr = 0 level = 0 parametersUseForLevel = 1 timingAdvance = 2147483647 },primary=CellSignalStrengthLte} result={ when=-28s752ms what=6 target=com.mediatek.internal.telephony.MtkSignalStrengthController }
01-04 14:05:49.201  2707  2707 D MtkSSCtr: [1] new:{level:0, raw:SignalStrength:{mAverageLevel=-1mCdma=CellSignalStrengthCdma: cdmaDbm=2147483647 cdmaEcio=2147483647 evdoDbm=2147483647 evdoEcio=2147483647 evdoSnr=2147483647 level=0,mGsm=CellSignalStrengthGsm: rssi=2147483647 ber=2147483647 mTa=2147483647 mLevel=0,mWcdma=CellSignalStrengthWcdma: ss=2147483647 ber=2147483647 rscp=2147483647 ecno=2147483647 level=0,mTdscdma=CellSignalStrengthTdscdma: rssi=2147483647 ber=2147483647 rscp=2147483647 level=0,mLte=CellSignalStrengthLte: rssi=2147483647 rsrp=2147483647 rsrq=2147483647 rssnr=2147483647 cqiTableIndex=2147483647 cqi=2147483647 ta=2147483647 level=0 parametersUseForLevel=1,mNr=CellSignalStrengthNr:{ csiRsrp = 2147483647 csiRsrq = 2147483647 csiCqiTableIndex = 2147483647 csiCqiReport = [] ssRsrp = 2147483647 ssRsrq = 2147483647 ssSinr = 2147483647 level = 0 parametersUseForLevel = 1 timingAdvance = 2147483647 },primary=CellSignalStrengthLte}}, 
01-04 14:05:51.475  2707  4209 D TranMimoRxController: onSignalStrengthsChanged: rsrp = -92, rsrq = -13
01-04 14:06:43.779  1536  1938 D RmmNwHdlr: [0] NR:state = 1, registred=1, plmn = 46001,pscPci = *E, nr_arfcn = 633984, cid = ****40104, tac = ***000, rsrp = 52, rsrq = 61,sinr = 50, ta = 268435455, csirsrp = 255, csirsrq = 255, band = 78,long_name = CHN-UNICOM, short_name = UNICOM, err = 0
01-04 14:06:46.020  2707  3098 D RILJ    : [UNSL]< UNSOL_CELL_INFO_LIST [CellInfoNr:{ mRegistered=YES mTimeStamp=94511263697ns mCellConnectionStatus=1 CellIdentityNr:{ mPci = 787 mTac = 10092544 mNrArfcn = 428910 mBands = [1] mMcc = 460 mMnc = 01 mNci = 41417397387 mAlphaLong = CHN-UNICOM mAlphaShort = UNICOM mAdditionalPlmns = {} } CellSignalStrengthNr:{ csiRsrp = 2147483647 csiRsrq = 2147483647 csiCqiTableIndex = 2147483647 csiCqiReport = [] ssRsrp = -99 ssRsrq = -11 ssSinr = 11 level = 1 parametersUseForLevel = 1 timingAdvance = 0 } }, CellInfoNr:{ mRegistered=NO mTimeStamp=94511263697ns mCellConnectionStatus=0 CellIdentityNr:{ mPci = 744 mTac = 21474

…(已截断，完整内容见源 JSON 对应记录的 normal_log)…
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
