---
name: com-data-ddsswitchfail
description: "「智能双卡切换失败」COMMON。拉 main/system/radio 对 patterns 出结论。"
---

# COM_DATA_DdsSwitchFail

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 智能双卡切换失败
- **特征**: 
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

- **切换数据卡到指定的卡**: `notifyPreferredDataSubIdChanged to`
- **记录数据副卡的subid和信号强度**: `TranPhoneSwitcher.*mOthersign`
- **记录数据主卡的subid和信号强度**: `TranPhoneSwitcher.*mDefaultsign`
- **获取当前数据卡的网络类型**: `TranPhoneSwitcher.*getNetworkType`
- **触发双卡切换功能**: `TranPhoneSwitcher.*switchData`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
行 20038: 09-23 20:59:42.801460  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G  //当前网络类型为4G
	行 20039: 09-23 20:59:42.801538  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1 //当前默认数据卡subid为1，信号强度评级为3
	行 20288: 09-23 20:59:45.536653  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 20289: 09-23 20:59:45.537078  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 20330: 09-23 20:59:45.785870  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 20331: 09-23 20:59:45.786374  2673  3534 I TranPhoneSwitcher: mOthersign:4subid :2 //当前非数据卡subid为2，信号强度评级为4
	行 20611: 09-23 20:59:48.412264  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 20612: 09-23 20:59:48.412456  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 20896: 09-23 20:59:50.908465  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 20897: 09-23 20:59:50.908728  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 20944: 09-23 20:59:51.180854  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 20945: 09-23 20:59:51.181152  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 21203: 09-23 20:59:53.863849  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 21204: 09-23 20:59:53.864371  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 21443: 09-23 20:59:56.024400  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 21444: 09-23 20:59:56.024920  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 21551: 09-23 20:59:57.771255  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 21552: 09-23 20:59:57.771813  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 22013: 09-23 21:00:00.656881  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 22014: 09-23 21:00:00.657171  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 22105: 09-23 21:00:01.138364  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 22107: 09-23 21:00:01.138553  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 22361: 09-23 21:00:03.460277  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 22362: 09-23 21:00:03.460831  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 22510: 09-23 21:00:06.270838  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 22511: 09-23 21:00:06.271119  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 22517: 09-23 21:00:06.334168  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 22518: 09-23 21:00:06.334701  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 24659: 09-23 21:00:11.796118  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 24660: 09-23 21:00:11.796174  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 24676: 09-23 21:00:11.801108  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 24678: 09-23 21:00:11.801216  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 25088: 09-23 21:00:12.097470  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 25089: 09-23 21:00:12.097577  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 26187: 09-23 21:00:14.801807  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 26188: 09-23 21:00:14.802027  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 26572: 09-23 21:00:15.741346  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 26573: 09-23 21:00:15.741424  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 26886: 09-23 21:00:16.490713  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 26887: 09-23 21:00:16.491232  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 27279: 09-23 21:00:17.574936  2673  3534 I TranPhoneSwitcher: isSmartDataSwitchEnabled,subid is :2
	行 27282: 09-23 21:00:17.578214  2673  3534 I TranPhoneSwitcher: mIsDefaultSmartSwitchOn:falseisDefaultSmartSwitchOntrue
	行 27283: 09-23 21:00:17.580810  2673  3534 I TranPhoneSwitcher: ServiceState is null :false
	行 27284: 09-23 21:00:17.581078  2673  3534 I TranPhoneSwitcher: ss.getState()0
	行 27525: 09-23 21:00:18.482549  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 27526: 09-23 21:00:18.482798  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 30741: 09-23 21:00:21.260417  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 30742: 09-23 21:00:21.260536  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 30999: 09-23 21:00:21.612184  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 31000: 09-23 21:00:21.612297  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 33251: 09-23 21:00:24.089867  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 33252: 09-23 21:00:24.089979  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 34174: 09-23 21:00:26.738035  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 34175: 09-23 21:00:26.738952  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 34256: 09-23 21:00:26.958765  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 34257: 09-23 21:00:26.958831  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 35967: 09-23 21:00:29.839821  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 35968: 09-23 21:00:29.839913  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 36758: 09-23 21:00:31.849816  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 36759: 09-23 21:00:31.849912  2673  3534 I TranPhoneSwitcher: mOthersign:3subid :2
	行 37144: 09-23 21:00:32.725029  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 37145: 09-23 21:00:32.725117  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 37384: 09-23 21:00:35.446761  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 37385: 09-23 21:00:35.450561  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 37456: 09-23 21:00:36.340493  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 37457: 09-23 21:00:36.340810  2673  3534 I TranPhoneSwitcher: mOthersign:4subid :2
	行 37836: 09-23 21:00:38.318030  2673  3534 D TranPhoneSwitcher: getNetworkType: 4G
	行 37837: 09-23 21:00:38.318088  2673  3534 I TranPhoneSwitcher: mDefaultsign:3subid :1
	行 38211: 09-23 21:00:39.939510  2673  3534 D TranPhoneSwit

…(已截断，完整内容见源 JSON 对应记录的 normal_log)…
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
