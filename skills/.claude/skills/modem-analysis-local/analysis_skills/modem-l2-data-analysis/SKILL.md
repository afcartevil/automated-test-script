---
name: modem-l2-data-analysis
description: 数据域 L2 主控 skill。仅负责首个子 skill 路由、调用编排与结论汇总，不做具体协议分析。结合 analysis.l0_baseline、analysis.l1_business、Jira 上下文和打包日志，写回 analysis.l2_domains.data。Use when L1 primary domain is `data`.
---

# L2 数据业务主控 Skill

在 L1 已将问题判定为 `data` 时使用。

## 主控职责边界（固定）

- 主控只做三件事：`首个子 skill 判断`、`子 skill 调用编排`、`结果汇总输出`。
- 主控不做具体分析逻辑；路由规则与汇总规则见 `references/playbook.md`。
- 子 skill 具体分析逻辑见各 `sub_skills/<id>/references/playbook.md`。

## Skip Rule (L0 Validity Gate)

If `analysis.l0_baseline.validity_gate.status == "invalid"` (or `analysis.l0_baseline.should_continue == false`), this skill MUST be skipped.

## 执行顺序（固定）

1. 读取 `references/playbook.md`（路由、编排、汇总规则）。
2. 按路由结果逐个执行子 skill：读取 `sub_skills/<id>/references/playbook.md` 并完成分析。
3. 按 `references/output-schema.md` 写回 `manifest.analysis.l2_domains.data`。

## 维护约定（重要）

| 要改的内容 | 改哪个文件 | 不要改 |
|-----------|-----------|--------|
| 主控路由 / 关键词 / 汇总规则 | `references/playbook.md` | 本 SKILL.md |
| manifest 输出结构 | `references/output-schema.md` | 本 SKILL.md |
| 子 skill 分析步骤 / 关键字 / 判定 / 输出字段 | `sub_skills/<id>/references/playbook.md` | 子 skill 的 SKILL.md |
| 工具用法 / 禁止写脚本 | `AI使用规则.md` | — |

**AI 必须以 playbook 为分析逻辑的唯一来源**；SKILL.md 仅提供入口与边界，不含会频繁变更的步骤细节。

## 边界说明

- 不改写 L1 业务判断结果。
- 不输出最终 Jira 报告（由 L3 负责）。
- 若上游已 short-circuit（如 L0 invalid），遵循上游流程。
- **主路径为 AI 读 Skill + playbook 执行**；`scripts/run_l2_data_analysis.py` 仅为占位/调试。

## 资源

- `references/playbook.md` — 主控路由与汇总（**分析逻辑来源**）
- `references/output-schema.md` — 输出结构
- `AI使用规则.md` — 工具用法与禁止临时脚本
- `sub_skills/` — 各子场景（逻辑在各子 playbook 中）
- `$log-search-read` — 日志搜索
- `scripts/pcap_analyzer.py` — PCAP 三段式分析
