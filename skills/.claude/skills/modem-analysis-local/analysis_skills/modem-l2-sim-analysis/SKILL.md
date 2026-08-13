---
name: modem-l2-sim-analysis
description: 对 SIM 卡相关场景做 L2 故障分析，结合 `analysis.l0_baseline`、`analysis.l1_business`、Jira 上下文和打包日志，提取时间线、关键证据和候选根因，并写回 `analysis.l2_domains.sim`。Use when L1 primary domain is `sim`.
---

# L2 SIM 卡业务分析

在 L1 已将问题判定为 `sim` 时使用这个 skill。

## 职责

- 围绕 SIM 卡识别、卡状态、注册相关异常建立故障时间线
- 识别卡检测、卡锁、卡状态切换、注册拒绝和对比差异
- 基于 AT+ESIMS 命令序列、ATR 响应、状态流转进行深度分析
- 输出 `analysis.l2_domains.sim`

## Skip Rule (L0 Validity Gate)

If `analysis.l0_baseline.validity_gate.status == "invalid"` (or `analysis.l0_baseline.should_continue == false`), this skill MUST be skipped.

脚本会自动检查 L0 validity gate，如果判定为无效，将返回 `SKIPPED` 状态。

---

## 执行步骤

### 步骤 1: 执行 L2 SIM 分析脚本

运行主分析脚本：

```bash
python scripts/run_l2_sim_analysis.py \
  --manifest /path/to/manifest.json
```

**可选参数**:
- `--log-root <path>`: 覆盖 manifest 中的 `final_log_root`
- `--output <path>`: 将分析结果额外保存到指定 JSON 文件
- `--skip-gate`: 跳过 L0 validity gate 检查（调试用）

**脚本功能**：

脚本会自动完成以下所有操作（AI 无需介入）：

1. **读取输入数据**
   - 从 manifest 读取 `analysis.l0_baseline` 和 `analysis.l1_business`
   - 从 manifest 读取 `final_log_root` 路径
   - 检查 L0 validity gate 状态

2. **日志扫描与证据提取**
   - 扫描 `radio_log`、`main_log`、`ps`、`system` 等日志文件
   - 提取 AT+ESIMS 命令序列（+ESIMS:inserted,cause）
   - 提取 updateSimState 状态流转记录
   - 检测 ATR 响应（AnswerToReset）
   - 识别 SIM 卡错误指示（MSG_ID_SIM_ERROR_IND）

3. **深度分析**
   - **步骤 1**: ATR 响应检测（硬件问题）
   - **步骤 2**: AT+ESIMS 序列解析（识别不识卡、救卡、热插拔异常）
   - **步骤 3**: updateSimState 状态流转分析（检测异常状态和掉卡）
   - **步骤 4**: 特殊场景检测（PIN 锁、eSIM 冲突、Modem crash、救卡流程）
   - **步骤 5**: 综合分类（按优先级判断问题类型）

4. **结果生成**
   - 构建时间线（合并 ESIMS 事件和状态变化）
   - 提取关键证据（ATR 错误、ESIMS 序列、状态异常）
   - 生成多个候选根因（带置信度和来源）
   - 生成解决建议（基于问题分类）
   - 标注缺失信息（gaps）和补充搜索建议

5. **写回 manifest**
   - 将分析结果写入 `manifest.analysis.l2_domains.sim`
   - 保存更新后的 manifest 文件

**脚本输出结构**：

```json
{
  // === 层次 1: 原始数据（AI 可以重新分析）===
  "at_esims_sequence": [
    {
      "timestamp": "2026-03-30T09:45:18",
      "slot": 0,
      "inserted_status": 1,
      "cause": 29,
      "interpretation": "SIM_DETECTED"
    }
  ],
  "state_flow": {
    "slot_0": [
      {"timestamp": "2026-03-30T09:45:18", "state": "UNKNOWN"}
    ]
  },
  "timeline": [
    {
      "timestamp": "2026-03-30T09:45:18",
      "slot": 0,
      "event_type": "sim_detected",
      "event_code": "+ESIMS:1,29",
      "description": "SIM_DETECTED",
      "log_source": "radio_log"
    }
  ],
  "evidence": [
    {
      "type": "at_esims",
      "content": "+ESIMS:1,29 (SIM_DETECTED)",
      "log_file": "radio_log",
      "timestamp": "2026-03-30T09:45:18",
      "relevance": "high",  // high/medium/low
      "slot": 0
    }
  ],
  
  // === 层次 2: 脚本的初步判断（AI 可以参考或质疑）===
  "problem_classification": "SIM_ACCESS_ERROR",
  "affected_slot": 0,
  "root_cause": "+ESIMS:1,29 后紧跟 +ESIMS:0,1，SIM 卡访问错误",
  "confidence": "high",  // high/medium/low
  "candidate_causes": [
    {
      "cause": "SIM 卡访问错误",
      "confidence": "high",
      "supporting_evidence": ["+ESIMS:1,29", "+ESIMS:0,1"],
      "source": "script_analysis"
    },
    {
      "cause": "间歇性接触不良",
      "confidence": "medium",
      "supporting_evidence": ["救卡流程成功"],
      "source": "recovery_analysis"
    }
  ],
  
  // === 层次 3: 脚本的不确定性（AI 应该深入探索）===
  "gaps": [
    {
      "type": "missing_logs",
      "description": "未找到 ATR 响应日志",
      "impact": "无法判断硬件状态",
      "suggestion": "使用 $log-search-read 搜索关键字：'ATR'、'AnswerToReset'"
    }
  ],
  
  // === 层次 4: 详细数据 ===
  "hardware_detection": {
    "atr_response": {"slot_0": "failed", "slot_1": "unknown"},
    "hot_plug_analysis": {
      "count": 2,
      "time_span": "",
      "abnormal_patterns": []
    }
  },
  "special_scenarios": {
    "pin_lock": {"detected": false, "slot": null},
    "esim_conflict": {"detected": false, "slot": null},
    "modem_crash": {"detected": false, "crash_type": null},
    "recovery_process": {"triggered": true, "success": true, "duration": "3.2s"}
  },
  "recommendations": [
    "清洁 SIM 卡触点",
    "交叉测试：将 SIM 卡插入其他设备"
  ],
  
  // === 层次 5: 分析元数据 ===
  "analysis_metadata": {
    "script_version": "2.0",
    "analysis_timestamp": "2026-05-19T10:30:00",
    "log_files_analyzed": ["radio_log", "main_log", "ps", "system"],
    "total_esims_events": 5,
    "total_state_changes": 3,
    "patterns_detected": ["DETECT_AFTER_ERROR"]
  },
  
  // === 层次 6: 原始数据统计（供 AI 发现异常）===
  "raw_data_summary": {
    "esims_causes_distribution": {"29": 2, "1": 2, "13": 1},
    "state_distribution": {
      "slot_0": {"UNKNOWN": 1, "ABSENT": 1, "READY": 1}
    }
  }
}
```

---

### 步骤 2: AI 深度分析与报告生成

**AI 任务**：

脚本已经提供了丰富的"原材料"，AI 需要基于这些数据进行深度推理和灵活判断。

#### 2.1 读取脚本输出

从 manifest 读取 `analysis.l2_domains.sim`，理解数据的多层次结构：

**层次 1: 原始数据**（AI 可以重新分析）
- `at_esims_sequence`: 完整的 AT+ESIMS 事件序列（未截断）
- `state_flow`: 完整的 SIM 卡状态流转记录
- `timeline`: 合并后的事件时间线
- `evidence`: 所有证据（带 `relevance` 标注：high/medium/low）

**层次 2: 脚本的初步判断**（AI 可以参考或质疑）
- `problem_classification`: 脚本的问题分类
- `root_cause`: 脚本的根因判断
- `confidence`: 脚本的置信度（high/medium/low）
- `candidate_causes`: 多个候选根因（带置信度和来源）

**层次 3: 脚本的不确定性**（AI 应该深入探索）
- `gaps`: 缺失的信息清单（带补充搜索建议）
- `analysis_metadata.patterns_detected`: 检测到的模式

**层次 4-6: 详细数据和统计**
- `hardware_detection`, `special_scenarios`, `recommendations`
- `raw_data_summary`: 统计分布（供 AI 发现异常模式）

#### 2.2 深度推理（AI 的核心价值）

AI 应该进行以下分析，而不是简单接受脚本的判断：

**A. 验证脚本判断的合理性**

示例：
```
脚本判断：SIM_ACCESS_ERROR（置信度 high）

AI 检查：
1. 查看 at_esims_sequence，确认是否真的是 29→1 模式 ✓
2. 查看 timeline，确认时间间隔（如果间隔很长，可能不是接触不良）
3. 查看 state_flow，确认最终状态（如果最终是 READY，可能已自动恢复）
4. 查看 special_scenarios.recovery_process（如果救卡成功，说明已恢复）

AI 结论：
- 如果最终状态是 READY 且救卡成功 → 修正为"间歇性接触不良，已自动恢复"
- 如果最终状态仍是 ABSENT → 确认为"SIM 卡访问错误，需要人工干预"
```

**B. 发现脚本未预设的异常模式**

示例：
```
脚本判断：UNKNOWN（置信度 low）

AI 分析 raw_data_summary：
- esims_causes_distribution: {"29": 5, "1": 5}
- 发现：反复出现 29→1 循环，每次间隔 2 秒

AI 推理：
- 这是典型的"SIM 卡芯片损坏"特征（脚本未预设此模式）
- 不是简单的接触不良（接触不良通常会触发救卡机制）

AI 建议：
- 更换 SIM 卡测试
- 如果更换后正常，确认为 SIM 卡芯片损坏
```

**C. 结合 Jira 上下文进行跨域分析**

示例：
```
脚本判断：NORMAL（SIM 卡识别正常）
Jira 描述：用户反馈"无法拨打电话"

AI 推理：
1. SIM 卡硬件层面正常（ATR 成功，状态 READY）
2. 但用户无法拨打电话，问题可能在网络注册层
3. 需要查看 L2 call 域的分析结果

AI 建议：
- SIM 卡无问题，建议检查网络注册和信号强度
- 查看 analysis.l2_domains.call 的分析结果
```

**D. 评估多个候选根因**

脚本提供了多个 `candidate_causes`，AI 应该：
- 结合 Jira 描述判断哪个更符合用户场景
- 如果用户提到"经常插拔 SIM 卡"，优先考虑"频繁热插拔"
- 如果用户提到"从未插拔"，排除"热插拔"相关原因

#### 2.3 补充搜索（当脚本数据不足时）

**触发条件**：
- `confidence` 为 `low`
- `problem_classification` 为 `UNKNOWN` 或 `INSUFFICIENT_EVIDENCE`
- `gaps` 列表不为空

**补充搜索步骤**：

1. **查看 gaps 中的建议**
   ```json
   {
     "type": "missing_logs",
     "description": "未在日志中找到 AT+ESIMS 或 updateSimState 记录",
     "suggestion": "使用 $log-search-read 搜索关键字：'SIM'、'ESIMS'、'updateSimState'"
   }
   ```

2. **使用 `$log-search-read` 补充搜索**
   - 搜索关键字：gaps 中建议的关键字
   - 时间范围：根据 Jira 描述或 L0 baseline 中的时间窗
   - 目标：寻找脚本未覆盖的日志片段

3. **分析补充数据**
   - 如果找到新的证据，更新判断
   - 如果仍无有效信息，在报告中说明

**注意**：
- ✅ 补充搜索是**可选的**，仅在必要时进行
- ✅ 大多数情况下，脚本提供的数据已经足够
- ❌ 不要为了"完整性"而盲目搜索所有可能的关键字

#### 2.4 生成最终报告

报告应包括：

**A. 问题摘要**
- 问题类型（基于 AI 的最终判断，可以不同于脚本）
- 受影响的卡槽
- 根本原因（用通俗语言解释）
- 置信度说明

**B. 关键证据解读**
- 从 `evidence` 中选取 `relevance: high` 的证据
- 用通俗语言解释每条证据的含义
- 说明证据如何支持根因判断

**C. 时间线分析**
- 从 `timeline` 中提取关键事件
- 按时间顺序描述问题发生过程
- 标注关键转折点（如救卡触发、状态变化）

**D. 技术细节**（可选，根据受众决定）
- 解读 `at_esims_sequence`（AT+ESIMS 命令序列）
- 解读 `state_flow`（SIM 卡状态流转）
- 解读 `hardware_detection`（硬件检测结果）
- 解读 `special_scenarios`（特殊场景）

**E. 根因分析**
- 综合所有证据给出最终判断
- 如果与脚本判断不同，说明理由
- 如果有多个候选根因，说明为什么选择某一个

**F. 解决建议**
- 基于 `recommendations` 生成具体的操作步骤
- 区分用户可自行操作的步骤和需要技术支持的步骤
- 提供预期效果和验证方法

**G. 后续行动项**
- 如果问题未完全解决，列出需要进一步收集的信息
- 从 `gaps` 中提取缺失的信息
- 建议下一步的调试方向

**H. 分析质量说明**（可选）
- 基于 `analysis_metadata` 说明分析的完整性
- 如果数据不足，明确说明限制
- 如果置信度较低，建议收集更多日志

#### 2.5 AI 的灵活性体现

**AI 可以做的**：
- ✅ 推翻脚本的初步判断（如果有充分理由）
- ✅ 发现脚本未预设的异常模式
- ✅ 进行补充搜索（当数据不足时）
- ✅ 跨域关联分析（结合 L0、L1、其他 L2 域）
- ✅ 结合 Jira 描述和用户反馈进行综合判断
- ✅ 提出脚本改进建议（如果发现新的模式）

**AI 不应该做的**：
- ❌ 盲目接受脚本判断，不进行验证
- ❌ 忽略 `gaps` 中的缺失信息
- ❌ 在数据充足时仍进行大量补充搜索（浪费时间）
- ❌ 生成与证据不符的结论

---

## 失败判定

脚本在以下情况输出 `SKILL_FAILED`:
- manifest 文件不存在或格式错误
- 脚本执行过程中发生未捕获的异常（如 Python 语法错误、依赖缺失）

以下情况**不视为失败**:
- 日志中未找到 SIM 相关记录 → 返回 `INSUFFICIENT_EVIDENCE`
- L0 validity gate 判定为无效 → 返回 `SKIPPED`
- 无法明确分类问题 → 返回 `UNKNOWN`
- `final_log_root` 不存在 → 返回 `INSUFFICIENT_EVIDENCE`

---

## 文件输出

本 skill 不生成独立的日志文件，所有分析结果直接写入 `manifest.json` 的 `analysis.l2_domains.sim` 字段。

如需保存分析报告，可使用 `--output` 参数：

```bash
python scripts/run_l2_sim_analysis.py \
  --manifest /path/to/manifest.json \
  --output /path/to/sim_analysis_result.json
```

---

## 边界

- 不改写 L1 业务判断
- 不输出最终面向人的总结报告（由 AI 在步骤 2 完成）
- 专注于 SIM 卡相关的技术分析

---

## 资源

### 核心文档
- `references/sim-playbook.md` - 5 步分析流程（脚本已实现）
- `references/sim-output-schema.md` - 输出结构定义

### 详细参考（供 AI 理解技术细节）
- `references/sim-at-esims.md` - AT+ESIMS 命令完整参考（含 0-29 全部状态码）
- `references/sim-hardware.md` - 硬件问题检测（ATR / 热插拔 / eSIM）
- `references/sim-state-flow.md` - SIM 卡状态流转分析
- `references/sim-log-keywords.md` - 日志搜索关键字清单
- `references/sim-examples.md` - 实际分析示例集
- `references/sim-frequent-report.md` - 频繁上报类问题分析

### 外部文档
- [SIM卡Skill开发](https://transsioner.feishu.cn/wiki/NEEBwlF1IiyVMWkXBP8cs7sEndb)
- [通信skill框架](https://transsioner.feishu.cn/wiki/FySdwXwoBiqBchkKnvKcIoCGnAN)

---

## 自测记录

**测试日期**: 待补充  
**测试人**: 待补充  
**测试用例**:

| Jira 单号 | 问题类型 | 测试结果 | 备注 |
|-----------|---------|---------|------|
| TOS163-27812 | SIM 卡不识别 | ✅ 通过 | 正确识别为 SIM_ACCESS_ERROR |
| OS162-36393 | PIN 锁 | ✅ 通过 | 正确识别为 PIN_LOCK |
| 待补充 | 救卡流程 | 待测试 | - |
| 待补充 | eSIM 冲突 | 待测试 | - |

**测试结论**: 待补充

---

**版本**: 2.0 (符合 Skills 编写标准 - 混合模式)  
**最后更新**: 2026-05-19
