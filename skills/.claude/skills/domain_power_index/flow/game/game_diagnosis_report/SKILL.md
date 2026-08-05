---
name: flow_power_game_diagnosis_report
description: 步骤12汇总后：确认功耗差、初步诊断、AI建议，并合并写入澄清报告 HTML。
---
## 功能描述
flow **步骤 14**（须在步骤 12 `game_summary` 之后；建议先跑步骤 13 `game_current_log_correlate`）。在 2~11 分维 JSON + 步骤 12 汇总 + 可选步骤 13 电流关联结果上完成：

1. **确认功耗差**：问题单 I1、电流图对比结论、排除已知软硬件差并分流  
2. **初步诊断**：测试手法不符 / 软件策略差异 / 功能差异 / 异常问题（规则引擎）  
3. **AI 判断与补充建议**  
4. **澄清报告**：全部合并写入 `game_power_clarify_report.html`（**不再单独输出** `game_diagnosis_report.html`）

原因规则由 [game_root_cause](../game_root_cause/SKILL.md) 的 `cause-judgment-rules.yaml` 执行；本 skill 负责功耗差闭合、AI 与报告合并。

## 1. 确认功耗差
| 子项 | 说明 |
|------|------|
| 问题单数据 | `test_power_ma` / `competitor_power_ma` / `delta_power_ma`(I1) |
| 电流图对比 | `waveform_analysis`：异常抬高段、对均值影响、去异常段后平均差 |
| 排除已知差 | `known_deltas` 或 `screen/speaker/cpu/rf_delta_ma` 求和得 I |
| 分流 | **I ≥ I1** → `known_delta_module`；**I &lt; I1** → `continue_analysis` |

## 2. 初步诊断重点
- **测试手法不符**（含子类日志不全）、**软件策略差异**、**功能差异**、**异常问题**
- 步骤对标见 [cause-attribution-mapping.yaml](../game_root_cause/references/cause-attribution-mapping.yaml)

## 输入参数
1. **log_path**（可选）  
2. **--meta-json** / CLI 功耗与已知差  
3. **--ai-json**（可选）外部 LLM 判断  

## 输出结果
写入 `<log_path>/analysis/`：
- `game_power_delta.json`
- `game_preliminary_diagnosis.json`
- `game_ai_insights.json`
- `game_diagnosis_report.json`（编排摘要）
- `game_root_cause.json`
- **`game_power_clarify_report.html`**（唯一总报告：原因说明 + 日志快照 + 子报告链接 + AI）
- 各步骤摘要 HTML：`game_brightness_report.html`、`game_thermal_report.html` 等（由 JSON 生成；汇总仪表板沿用 `game_power_report.html`）

## 使用方法
```bash
python analysis/domain/power/flow/game/game_diagnosis_report/scripts/game_diagnosis_report.py \
  --jira-key PROJ-123 \
  --test-power-ma 920 --competitor-power-ma 850 --delta-power-ma 70 \
  --screen-delta-ma 20 --speaker-delta-ma 5 \
  --has-abnormal-spike false
```

## 注意事项
- 与澄清报告重叠的「测试数据 / 器件拆解 / 原因分析」只保留在澄清报告中  
- 无 I1 时仍输出诊断与 AI，分流为 `need_power_meta`  
- 勿再打开已删除的 `game_diagnosis_report.html`
