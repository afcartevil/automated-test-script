---
name: mtk-sim-simdetect
description: "「识卡异常」MTK；无法识别到sim卡、状态栏不显示信号塔、SIM卡状态更新不及时、SIM卡状态异常。拉 main/system/radio 对 patterns 出结论。"
---

# MTK_SIM_SimDetect

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 识卡异常
- **特征**: 无法识别到sim卡、状态栏不显示信号塔、SIM卡状态更新不及时、SIM卡状态异常
- **平台边界**: 与 **MTK** 机型或 Jira 芯片字段一致时使用。
- **补充**: 识卡异常类问题

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

- **eSIM相关AT命令**: `AT.*ESIMS`
- **接收SIM状态改变指示（带原因）**: `RECV.*SIM_STATUS_CHANGE_WITH_CAUSE_IND`
- **处理SIM状态改变**: `RmmSimCommUrc.*handleSimStateChanged`
- **SIM卡PIN码验证**: `AT.*CPIN`
- **eSIM PIN码相关命令**: `AT.*EPINC`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
// ==================== 阶段1: SIM卡插入检测 ====================
11-06 19:17:28.078688  1672  1694 I AT      : [0] AT< +ESIMS: 1,12 (RIL_URC_READER, tid:492594703536) //MTK Modem上报SIM卡插入事件(1:已插入,12:插入原因)
11-12 16:05:20.479098  1183  1675 I AT      : RECV MSGID=4505 [SIM_STATUS_CHANGE_WITH_CAUSE_IND], TXID=ffff, DUMP=841954240000000001000545FFFF10000001010000000000010101000B000000 //MIPC收到SIM状态变更消息
11-12 16:05:20.479832  1183  1686 I RmmSimCommUrc: [0] handleSimStateChanged, +ESIMS:1,12 //RIL处理SIM卡插入事件
// ==================== 阶段2: 查询PIN码状态 ====================
11-06 19:17:29.565090  1672  1706 I AT      : [0] AT> AT+CPIN? (RIL_CMD_READER_3, tid:492579609776) //RIL查询SIM卡PIN码状态
11-06 19:17:29.572395  1672  1705 I AT      : [0] AT< +CPIN: SIM PIN (RIL_CMD_READER_3, tid:492580674736) //Modem返回需要PIN码验证
11-06 19:17:30.205229  1672  1706 I AT      : [0] AT> AT+CPIN=*** (RIL_CMD_READER_3, tid:492579609776) //RIL发送PIN码进行SIM卡解锁
// ==================== 阶段3: 查询密码尝试次数 ====================
11-06 19:17:07.013180  1672  1706 I AT      : [0] AT> AT+EPINC (RIL_CMD_READER_3, tid:492579609776) //MTK扩展命令查询密码剩余尝试次数
11-06 19:17:07.019545  1672  1705 I AT      : [0] AT< +EPINC: 3, 3, 10, 10 (RIL_CMD_READER_3, tid:492580674736) //返回PIN1=3次,PIN2=3次,PUK1=10次,PUK2=10次
// ==================== 阶段4: SIM卡启用确认 ====================
11-06 19:17:28.745828  1672  1696 I AT      : [1] AT< +ESIMS: 1,29 (RIL_URC2_READER, tid:492590492848) //MTK Modem上报SIM卡启用状态(29:ENABLE)
11-12 16:05:50.920604  1183  1686 I RmmSimCommUrc: [0] handleSimStateChanged, +ESIMS:1,29 //RIL处理SIM卡启用事件
// ==================== 阶段5: 上层状态更新 ====================
11-06 19:17:29.670660  2611  2611 D UiccController: onGetIccCardStatusDone: phoneId-0 IccCardStatus: IccCardState {CARDSTATE_PRESENT,PINSTATE_ENABLED_NOT_VERIFIED,num_apps=1,gsm_id=0{APPTYPE_USIM,APPSTATE_PIN,pin1=PINSTATE_ENABLED_NOT_VERIFIED,pin2=PINSTATE_UNKNOWN}} //UiccController获取SIM卡状态完成
11-06 19:17:45.283975  2611  2611 D UiccController: Broadcasting intent ACTION_SIM_STATE_CHANGED READY reason null for phone: 0 //系统广播SIM卡READY状态
11-06 19:17:50.495336  2611  2611 D UiccController: Broadcasting intent ACTION_SIM_STATE_CHANGED LOADED reason null for phone: 0 //系统广播SIM卡LOADED状态(文件加载完成)
// ==================== 阶段6: SIM卡文件加载 ====================
11-06 19:17:50.500000  2611  2650 D SIMRecords: [0] fetchSimRecords: reading EF_IMSI //开始读取IMSI文件
11-06 19:17:50.501000  2611  2650 D SIMRecords: [0] fetchSimRecords: reading EF_ICCID //开始读取ICCID文件
11-06 19:17:50.502000  2611  2650 D SIMRecords: [0] fetchSimRecords: reading EF_AD //开始读取AD文件
11-06 19:17:50.510000  2611  2650 D IccFileHandler: [0] EVENT_GET_RECORD_SIZE_DONE: fileid=0x6F07 //获取文件记录大小完成
11-06 19:17:50.511000  2611  2650 D IccFileHandler: [0] EVENT_READ_RECORD_DONE: fileid=0x6F07 //读取文件记录完成
11-06 19:17:50.520000  2611  2650 D SIMRecords: [0] onAllRecordsLoaded: record load complete //所有SIM卡记录加载完成
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
