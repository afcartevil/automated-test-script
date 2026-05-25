---
name: com-data-dataunstable
description: "「数据连接不稳定」COMMON；数据频繁断开、数据不稳定、数据关闭失败、数据异常断开。拉 main/system/radio 对 patterns 出结论。"
---

# COM_DATA_DataUnstable

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 数据连接不稳定
- **特征**: 数据频繁断开、数据不稳定、数据关闭失败、数据异常断开
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

- **发起数据连接建立请求**: `.*> SETUP_DATA_CALL.*`
- **数据连接建立请求收到响应**: `.*< SETUP_DATA_CALL.*`
- **断开数据连接请求**: `.*> DEACTIVATE_DATA_CALL.*`
- **断开数据连接请求收到响应**: `.*< DEACTIVATE_DATA_CALL.*`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
01-04 14:05:54.941  2707  4403 D RILJ    : [0299]> SETUP_DATA_CALL,reason=NORMAL,accessNetworkType=EUTRAN,dataProfile=[DataProfile=[ApnSetting] CTNET, 2719, 46011, ctnet, , null, , null, null, 3, hipri | default | xcap | vsim, IPV4V6, IPV4V6, true, 0, true, 0, 0, 0, 0, 0, null, , false, UNKNOWN, UNKNOWN, 0, -1, -1, false, 3, 509404525, false, UNEDITED, TrafficDescriptor={mDnn=ctnet, null}, preferred=true],allowRoaming=false,linkProperties=null,pduSessionId=0,sliceInfo=null,trafficDescriptor=TrafficDescriptor={mDnn=ctnet, null},matchAllRuleAllowed=true [PHONE0]
01-04 14:05:54.990  2707  3130 D RILJ    : [0299]< SETUP_DATA_CALL DataCallResponse: { cause=NONE(0x0) retry=-1 cid=202 linkStatus=2 protocolType=2 ifname=ccmni2 addresses=[10.231.83.128/32, 240e:430:2aa0:b4b4::1/64] dnses=[/240e:47:0:702::1, /240e:47:0:701::1, /61.128.128.68, /61.128.192.68] gateways=[/10.231.83.128, /::] pcscf=[] mtu=0 mtuV4=0 mtuV6=0 handoverFailureMode=unknown pduSessionId=0 defaultQos=EpsQos { qosClassId=6 downlink=Bandwidth { maxBitrateKbps=0 guaranteedBitrateKbps=0} uplink=Bandwidth { maxBitrateKbps=0 guaranteedBitrateKbps=0}} qosBearerSessions=[] sliceInfo=null trafficDescriptors=[] networkValidationStatus=unsupported} [PHONE0]
01-04 14:06:27.473  2707  4403 D RILJ    : [0954]> DEACTIVATE_DATA_CALL cid = 202 reason = NORMAL [PHONE0]
01-04 14:06:27.643  2707  4545 D RILJ    : [0954]< DEACTIVATE_DATA_CALL  [PHONE0]
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
