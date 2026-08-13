---
name: modem-l3-conclusion
description: 汇总 L0 基础指标、L1 业务判断和 L2 域内分析结果，生成最终结论、解决建议和可回写 Jira 的报告文本。AI 必须按照本文档和 playbook.md 执行分析，不要调用脚本。
---

# L3 结论与建议

在 L0/L1/L2 分析完成后使用这个 skill。

## 职责

- 汇总 L0、L1、L2 结果形成最终结论
- 明确主要根因、次要影响因素、证据支撑
- 生成最终报告文本

## 前置条件

- `manifest.analysis.l0_baseline` 已完成
- `manifest.analysis.l1_business` 已完成
- `manifest.analysis.l2_domains.*` 已完成（根据 L1 路由结果）

## 输入

- `manifest.analysis.l0_baseline`: L0 基础指标
- `manifest.analysis.l1_business`: L1 业务判断
- `manifest.analysis.l2_domains.*`: L2 域内分析

## 输出

更新 `manifest.analysis.l3_conclusion` 和 `manifest.analysis.final_report`，包含：
- `conclusion_type`: 结论类型
- `primary_root_cause`: 主要根因
- `recommendations`: 建议下一步
- `final_report`: 最终报告文本

## 完成定义（DoD）

L3 完成时必须同时满足：

- `analysis.l3_conclusion.status == "completed"`
- `analysis.final_report` 非空
- `analysis.final_report` 以 `## 分析结论` 开头（允许前置空白行）
- `analysis.final_report` 可被 orchestrator 直接原文交付，不需要二次改写

## 执行步骤

详见 `references/playbook.md`。

## 边界

- 不重新搜索大批日志（使用已有 L0/L1/L2 结果）
- 不重新做业务分类（使用 L1 结果）
- 不直接回写 Jira（由 `$jira-comment-poster` 负责）

## 资源

- `references/playbook.md` - 详细分析步骤
- `references/report-template.md` - 报告模板
- `references/output-schema.md` - 输出格式
