---
name: mtk-sim-statusbaricon
description: "「状态栏图标显示异常」MTK；状态栏volte图标、状态栏vowifi图标、状态栏HD图标、状态栏vonr图标、状态栏网络制式图标。拉 main/system/radio 对 patterns 出结论。"
---

# MTK_SIM_StatusBarIcon

## 何时加载

在分析 Jira/Android 缺陷时，若问题与下列 **场景**、**特征** 相符，且满足 **平台边界**，应加载本 skill。

- **场景**: 状态栏图标显示异常
- **特征**: 状态栏volte图标、状态栏vowifi图标、状态栏HD图标、状态栏vonr图标、状态栏网络制式图标
- **平台边界**: 与 **MTK** 机型或 Jira 芯片字段一致时使用。
- **补充**: 网络类型/volte/vowifi/vowifi/HD等图标显示不符合要求

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

- **状态栏获取wificalling等状态**: `ImsConnectionStateListener`
- **处理IMS功能能力改变**: `ImsPhoneCallTracker.*handleFeatureCapabilityChanged`

## 正常流程参考日志 (normal_log)

以下仅供对比；若与现网 log 等级不一致，部分行可能不存在。

```
08-29 21:56:22.057784  2366 13159 I SysUI(250630)_MobileConnectionRepository_MtkImsConnectionStateListener: subId=3, onImsConnected STATE_IN_SERVICE, imsRadioTech = 3
08-29 21:56:22.058529  2366 13159 I MobileConnectionRepository_MtkImsConnectionStateListener: onFeatureCapabilityStateAdapter: disabledCapabilities=[-1, 1, 2, 3, -1, 5], enabledCapabilities=[0, -1, -1, -1, 4, -1]
08-29 21:56:22.058634  2366 13159 I MobileConnectionRepository_MtkImsConnectionStateListener: subId=3, updateIms: mImsRadioTech=3, mImsCap=0,isDisableWfc=false, isInService=true, isImsOverWfc=false, isImsOverVoice=true  //system UI获取到当前ims状态，关闭wificalling，在服务中，不在vowifi状态下，VoLTE状态为true
08-29 21:56:22.065747  2366 13159 I SysUI(250630)_MobileConnectionRepository_MtkImsConnectionStateListener: subId=3, onCapabilitiesStatusChanged:MmTel Capabilities - [Voice: true Video: false UT: true SMS: true CALL_COMPOSER: false BUSINESS_COMPOSER_ONLY: false]
08-29 21:57:25.399229  2597  2597 D ImsPhoneCallTracker: [0] handleFeatureCapabilityChanged: MmTel Capabilities - [Voice: true Video: false UT: true SMS: true CALL_COMPOSER: false BUSINESS_COMPOSER_ONLY: false] isVideoEnabledStateChanged=false
08-29 21:57:25.400170  2597  2597 D ImsPhoneCallTracker: [0] handleFeatureCapabilityChanged: isVolteEnabled=true, isVideoCallEnabled=false, isVowifiEnabled=false, isUtEnabled=true  //ims状态变化，volte打开，vilte关闭，wificall关闭，Ut是补充业务打开
```

---

## 经验库融合（按需 / 渐进加载）

本节承接原 `TEMP/comm_skill` 已拆出并吸收的能力。**分析时优先使用本文件前半部分的 patterns / 正常流程**；下列材料在会话中按需单独打开，避免一次性通读。

1. **通用口径**：`../com-comm-analysis-foundation/SKILL.md` 与同目录 `references/`（**`leaf-skill-routing.md`**：现象/Jira→各叶子目录名；**`problem-routing-index.md`**：域与主/辅专题；以及统一输出模板、日志收集、升级接力、术语、V2 强化、资料清单等）。
2. **原始 SOP / 培训稿 / Skill 设计文档**：`../com-comm-sop-source-archive/`（含 `source-text/`、`docs/`、原 `README.md`）。
3. **本目录专题参考文献**（若存在）：本目录 `references/` 下与通信经验库同名的专题 `.md` 副本；**仅当现象跨入 Call / Network / SIM / Stability 时再按需打开**，并遵守「1 个主专题 + 最多 1 个辅助专题」（见 foundation 中 `references/problem-routing-index.md`）。
