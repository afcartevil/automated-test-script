---
name: uns-sim-operatorname
description: "「状态栏运营商名称显示异常」UNISOC。拉 main/system/radio 对 patterns 出结论。"
---

# UNS_SIM_OperatorName

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 状态栏运营商名称显示异常
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

- **根据获取的spn和plmn更新显示**: `SST.*updateSpnDisplay`
- **网络返回的名称**: `RILJ.*<.*OPERATOR`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
08-29 20:50:48.893530  2597  2966 D RILJ    : [2037]< OPERATOR {Movistar, Movistar, 74000} [PHONE0]  //OPERATOR上报phone 0的运营商长名和短名为Movistar
08-29 21:56:22.074913  2597  2597 D MTKSST  : [GsmSST0] setImsRegistrationState: {registered=true mImsRegistrationOnOff=true}
08-29 21:56:22.081477  2597  2597 D MTKSST  : [GsmSST0] updateSpnDisplay: rawPlmn = Movistar  //获取到ServiceState的长名为Movistar
08-29 21:56:22.081603  2617  2617 I ImsService: updateImsRegstration[0], regstate:3, tech:-1, reason:ImsReasonInfo :: {1000 : CODE_REGISTRATION_ERROR, 0, 0}
08-29 21:56:22.081631  2597  2597 D MTKSST  : [GsmSST0] updateSpnDisplay: rawSpn = Movistar  //根据mccmnc获取的spn为Movistar
08-29 21:56:22.081791  2597  2597 D MTKSST  : [GsmSST0] updateSpnDisplay: rule = 3
08-29 21:56:22.115044  2597  2597 D MTKSST  : [GsmSST0] TDD updateSpnDisplay mSS.getOperatorNumeric() = 74000  //获取到ServiceState的mccmnc为74000
08-29 21:56:22.115185  2597  2597 D MTKSST  : [GsmSST0] TDD getNumeric simNumeric = 74000, operatorNumeric = 74000
08-29 21:56:22.115276  2597  2597 D MTKSST  : [GsmSST0] TDD currentMccEqualsSimMcc simNumeric = 74000, operatorNumeric = 74000
08-29 21:56:22.625065  2597  2597 D MTKSST  : [GsmSST0] RAT switched LTE -> Unknown at cell -1
08-29 21:56:22.630676  2597  2597 D MTKSST  : [GsmSST0] updateSpnDisplay: rawSpn = Movistar
08-29 21:56:22.631010  1670  1690 I AT      : [0] AT< OK (RIL_CMD_READER_1, tid:516413578416)
08-29 21:56:22.630906  2597  2597 D MTKSST  : [GsmSST0] updateSpnDisplay: rule = 2
08-29 21:56:22.631698  1670  1691 I AT      : [0] AT> AT+ECAMPUI=0 (RIL_CMD_READER_1 tid:516412513456)
08-29 21:56:22.633075  2597  2597 D MTKSST  : [GsmSST0] TDD updateSpnDisplay mSS.getOperatorNumeric() = null
08-29 21:56:22.633204  2597  2597 D MTKSST  : [GsmSST0] TDD getNumeric simNumeric = 74000, operatorNumeric = null
08-29 21:56:22.633238  2597  2597 D MTKSST  : [GsmSST0] TDD currentMccEqualsSimMcc simNumeric = 74000, operatorNumeric = null
08-29 21:56:22.634190  2597  2597 D MTKSST  : [GsmSST0] updateSpnDisplay: updateSpnDisplay: changed sending intent, rule=2, showPlmn='true', plmn='No service', showSpn='false', spn='null', dataSpn='Movistar', subId='3'  //状态更新为显示plmn，plmn为No service，不显示spn，spn为空
08-29 21:57:23.425834  2597  2966 D RILJ    : [2600]< OPERATOR {, , } [PHONE0]
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
