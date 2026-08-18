---
schema_version: "1.0"
name: "connectivity-spn-workflow"
parent: "connectivity"
department: "connectivity"
version: "1.0.0"
published_at: "2026-08-05"
deprecated_date: null
knowledge_type: "domain"
risk_tags: [spn, telephony, displayName, gerrit, jira]
module_map: "module-map.json"
scenarios: "scenarios.yaml"
rules: "rules.yaml"
match_threshold: 0.6
---

# connectivity / SPN Workflow

> SPN / 运营商名称 / displayName 的 Jira 驱动工作流知识包。编排见 `workflow.yaml`；Agent 执行正文以 SkillHub `spn-workflow` skill 为准。

## 领域定位

覆盖状态栏/锁屏/手动搜网/MVNO/云网 SPN/displayName 等问题，从 Jira+日志分析到 diff 确认、分支解析与 Gerrit 提交。平台分 MTK/QCOM，不得混改。

## 任务路由

| 用户需求 | 场景 ID | reference / 编排 |
|---|---|---|
| 读 Jira / 提供日志 / 开始 SPN 分析 | `spn-workflow-intake` | `references/workflow.md`, `workflow.yaml` |
| 日志分析 / 平台识别 / 根因报告 | `spn-workflow-analysis` | `references/mtk.md`, `references/qcom.md`, `references/report-template.md` |
| 改 telephony 源码 / 展示 diff | `spn-workflow-patch` | `workflow.yaml`, `spn-code-edit` skill |
| 分支解析 / 自检 / Gerrit 提交 | `spn-workflow-submit` | `references/submission.md`, `spn-submit` skill |

## 最小安全边界

1. 未完成分析不得改码。
2. 未确认 diff 不得提交。
3. Jira 版本、workspace manifest、Gerrit 分支三者不一致时停止提交。
4. MTK/QCOM 路径不得混搭。
5. 不得手拼 `git push refs/for/*` 或 `repo upload`。

## CLI 入口

```text
harness --json knowledge route --path connectivity/sub/spn
harness --json knowledge search "SPN 运营商名称 displayName"
harness --json knowledge read connectivity/sub/spn/workflow.yaml
```
