---
name: com-network-roamingstate
description: "「漫游状态异常」COMMON；漫游状态判断异常。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# COM_NETWORK_RoamingState

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 漫游状态异常
- **特征**: 漫游状态判断异常
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

- **服务状态跟踪漫游状态信息**: `SST.*updateRoamingState`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
R006AC9  01-13 18:10:03.478  1846  1846 D SST     : [1] updateRoamingState: roaming is false,currentNumericPlmn is,currentSimNumeric is
R006C03  01-13 18:10:03.589  1846  1846 D SST     : [1] updateRoamingState: roaming is false,currentNumericPlmn is,currentSimNumeric is
R006EFB  01-13 18:10:04.256  1846  1846 D SST     : [0] updateRoamingState: roaming is false,currentNumericPlmn is,currentSimNumeric is28601
R0071C6  01-13 18:10:04.504  1846  1846 D SST     : [0] updateRoamingState: roaming is false,currentNumericPlmn is,currentSimNumeric is28601
R009FDC  01-13 18:10:49.734  1846  1846 D SST     : [0] updateRoamingState: roaming is false,currentNumericPlmn is,currentSimNumeric is28601
R00A21E  01-13 18:10:51.072  1846  1846 D SST     : [0] updateRoamingState: resource override set non roaming.isSameNamedOperators=true,isOperatorConsideredNonRoaming=false
R00A21F  01-13 18:10:51.072  1846  1846 D SST     : [0] updateRoamingState: roaming is false,currentNumericPlmn is28602,currentSimNumeric is28601
R00AD1E  01-13 13:10:52.202  1846  1846 D SST     : [0] updateRoamingState: resource override set non roaming.isSameNamedOperators=true,isOperatorConsideredNonRoaming=false
R00AD1F  01-13 13:10:52.202  1846  1846 D SST     : [0] updateRoamingState: roaming is false,currentNumericPlmn is28602,currentSimNumeric is28601
R00BA47  01-13 13:10:53.331  1846  1846 D SST     : [0] updateRoamingState: resource override set non roaming.isSameNamedOperators=true,isOperatorConsideredNonRoaming=false
R00BA48  01-13 13:10:53.331  1846  1846 D SST     : [0] updateRoamingState: roaming is false,currentNumericPlmn is28602,currentSimNumeric is28601
R00BC59  01-13 13:10:53.649  1846  1846 D SST     : [1] updateRoamingState: roaming is false,currentNumericPlmn is,currentSimNumeric is
R00C3DC  01-13 13:10:54.533  1846  1846 D SST     : [0] updateRoamingState: resource override set non roaming.isSameNamedOperators=true,isOperatorConsideredNonRoaming=false
R00C3DD  01-13 13:10:54.534  1846  1846 D SST     : [0] updateRoamingState: roaming is false,currentNumericPlmn is28602,currentSimNumeric is28601
从log中可以看出plmn为28602，sim卡mccmnc为28601，但是系统判定为非漫游状态，原因是isSameNamedOperators为true，判断为同名运营商，所以不算漫游
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
