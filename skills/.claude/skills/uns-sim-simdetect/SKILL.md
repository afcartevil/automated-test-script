---
name: uns-sim-simdetect
description: "「识卡异常」UNISOC。拉 main/system/radio 对 patterns 出结论。"
funcType: "AI故障分析"
category: "通信"
---

# UNS_SIM_SimDetect

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 识卡异常
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

- **扩展来电显示AT命令**: `AT.*ECIND`
- **RIL层扩展来电显示AT命令**: `RIL-AT.*ECIND`
- **网络注册状态查询AT命令**: `AT.*XX`
- **RIL层网络注册状态查询AT命令**: `RIL-AT.*XX`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
// ==================== 阶段1: SIM卡插入检测 ====================
11-14 10:09:03.607   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,100 (RIL_URC_READER, tid:492594703536) //SPRD Modem上报SIM卡插入事件(3:SIM类型,100:SIM热插拔插入)
// ==================== 阶段2: SIM卡初始化中 ====================
   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,2 (RIL_URC_READER, tid:492594703536) //SPRD Modem上报SIM卡初始化中(2:正在初始化或验证)
// ==================== 阶段3: 查询SIM卡类型 ====================
11-14 10:09:03.609   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,6,255,3 (RIL_URC_READER, tid:492594703536) //SPRD Modem上报SIM卡类型信息(6:SIM类型,255:未知,3:具体类型参数)
// ==================== 阶段4: 查询PIN码剩余尝试次数 ====================
11-14 10:07:03.345   818   855 D RIL-AT  : Channel2: AT> AT+XX=0 (RIL_CMD_READER, tid:492579609776) //SPRD平台查询PIN1剩余尝试次数的AT命令(0:PIN1)
11-14 10:07:03.346   818  1137 D RIL-AT  : Channel2: AT< +XX: 3 (RIL_CMD_READER, tid:492580674736) //Modem返回PIN1剩余3次尝试机会
// 如需查询其他密码状态，继续发送对应命令
11-14 10:07:03.350   818   855 D RIL-AT  : Channel2: AT> AT+XX=2 (RIL_CMD_READER, tid:492579609776) //查询PUK1剩余尝试次数(2:PUK1)
11-14 10:07:03.351   818  1137 D RIL-AT  : Channel2: AT< +XX: 10 (RIL_CMD_READER, tid:492580674736) //Modem返回PUK1剩余10次尝试机会
// ==================== 阶段5: SIM卡锁定状态检查 ====================
11-14 10:09:03.610   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,4,0 (RIL_URC_READER, tid:492594703536) //SPRD Modem上报SIM卡锁定状态(4:锁定状态,0:未锁定)
// ==================== 阶段6: SIM卡准备就绪 ====================
11-14 10:09:03.611   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,2,1 (RIL_URC_READER, tid:492594703536) //SPRD Modem上报SIM卡初始化完成(2:初始化完成)
11-14 10:09:03.612   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,0 (RIL_URC_READER, tid:492594703536) //SPRD Modem上报SIM卡就绪(0:SIM ready)
11-14 10:09:03.613   818  1137 D RIL-AT  : Channel0: AT< +ECIND: 3,5 (RIL_URC_READER, tid:492594703536) //SPRD Modem再次确认SIM卡就绪(5:指示SIM ready)
// ==================== 阶段7: 上层状态更新和广播 ====================
11-14 10:09:03.614   818   856 D RILJ    : [0] UNSOL_RESPONSE_SIM_STATUS_CHANGED //RIL Java层收到SIM状态变更通知
11-14 10:09:03.615  2611  2611 D UiccController: [0] updateSimState: READY //Uicc控制器更新SIM卡状态为READY
11-14 10:09:03.616  2611  2611 D UiccController: Broadcasting intent ACTION_SIM_STATE_CHANGED READY reason null for phone: 0 //系统广播SIM卡READY状态
11-14 10:09:05.617  2611  2611 D UiccController: Broadcasting intent ACTION_SIM_STATE_CHANGED LOADED reason null for phone: 0 //系统广播SIM卡LOADED状态(文件加载完成)
11-14 10:09:05.618  2611  2611 D UiccController: Broadcasting intent ACTION_SIM_APPLICATION_STATE_CHANGED LOADED for phone: 0 slot: 0 port: 0 //系统广播SIM卡应用状态变更
// ==================== 阶段8: 网络注册准备完成 ====================
11-14 10:09:05.619  2611  2611 D TelephonyRegistry: [0] notifySimStateChange: READY->LOADED //电话注册表通知SIM状态变化
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
