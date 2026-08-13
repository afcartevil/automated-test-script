---
name: carrierconfig-tools
description: "CarrierConfig/APN 开发主控 Skill。从 Jira 需求到 Gerrit 提交的全流程编排。"
---

# CarrierConfig Tools（主控）

传音 CarrierConfig 开发的 AI 辅助工作流主控入口。按用户描述调度下列子 Skill，逐步完成需求分析、落点判定、XML 修改与提交。

## 子 Skill（按典型流程顺序）

| 顺序 | Skill ID | 路径 | 职责 |
|------|----------|------|------|
| 1 | jira-reader | `carrierconfig-tools/jira-reader/SKILL.md` | 读 Jira、解析需求、输出修改建议 |
| 2 | carrier-lookup | `carrierconfig-tools/carrier-lookup/SKILL.md` | 查矩阵、确认运营商与落点文件 |
| 3 | carrierconfig-edit | `carrierconfig-tools/carrierconfig-edit/SKILL.md` | 修改 CarrierConfig XML |
| 4 | carrierconfig-submit | `carrierconfig-tools/carrierconfig-submit/SKILL.md` | 台账、Gerrit 提交与通知 |
| — | matrix-update | `carrierconfig-tools/matrix-update/SKILL.md` | 补录矩阵（用户手动触发） |
| — | jira-ops | `jira-ops/SKILL.md` | Jira API（读单、评论等）；CAPTCHA/凭据问题时用 TAHP_USER_INPUT 向用户索取 |

共享数据与脚本：`carrierconfig-tools/shared/`（含 `data/carrier_keys_matrix.xlsx`）。

## 执行原则

1. **先 Read 本文件**，再按场景 Read 对应子 Skill 全文，严格按 SOP 执行。
2. 用户已在表单提供「描述」时，从中提取 Jira、运营商、mccmnc、key、期望值等，**勿重复询问已有信息**。
3. 需要用户确认或补充无法推断的参数时，输出 `=== TAHP_USER_INPUT ===` 块（见 Console BFF 人机协同协议），然后停止本轮输出等待用户提交。
4. 每完成一个主要阶段，输出「当前步骤 / 结论 / 下一步」。
5. 全部流程结束后输出结构化总结，须含：
   - ## 任务规划回顾
   - ## 已使用的 Skill
   - ## 文件修改清单
   - ## 升级/适配结果摘要
   - ## 风险与待用户确认项

## 典型流程

```
用户描述 → jira-reader（若有 Jira）→ carrier-lookup → 用户确认落点
         → carrierconfig-edit → 用户确认 diff → carrierconfig-submit
```

矩阵缺失时提示用户是否执行 `matrix-update`。

## 人机协同（Console 弹窗）

当需要用户确认身份、落点、diff 或补充路径/凭证时：

```
=== TAHP_USER_INPUT ===
request_id: <唯一 ID>
title: <弹窗标题>
message: <说明>
timeout_sec: 300
field.<name>.label: <显示名>
field.<name>.type: text|textarea
field.<name>.required: true|false
field.<name>.placeholder: <占位>
=== END_TAHP_USER_INPUT ===
```

用户提交后 BFF 会以「用户已提交配置」消息继续对话；请据此执行后续步骤。
