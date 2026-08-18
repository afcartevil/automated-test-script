# SPN Workflow

Jira 驱动的 SPN / 运营商名称 / displayName 工作流最小正文。完整状态机见 `workflow.yaml`；Agent 正文见 SkillHub `spn-workflow` skill。

## 入口判断

从 Jira 或用户描述抽取：

| 字段 | 用途 |
|---|---|
| `jira_id` | intake、提交说明、CR 关联 |
| `project_name` | project-info / 分支矩阵 |
| `affected_version` | 版本服务与 workspace 对齐 |
| `operator` / `mccmnc` | 现象与配置核对 |
| `symptom` | 选手动搜网/状态栏/MVNO/云网/注入链路 |
| `log_path` | 平台识别与分析 |

缺日志时只输出采集清单。缺 workspace 时可分析，不可改码或提交。

## 状态机

```text
INTAKE → ANALYZED → PATCHED → DIFF_APPROVED → BRANCH_RESOLVED → VERIFIED → SUBMITTED
```

禁止跳过。分析不自动改码；改码不自动提交；未确认 diff 不得 push。

## Harness CLI 映射

| 阶段 | CLI |
|---|---|
| Jira intake | `harness --json jira get --issue <KEY>` |
| 项目/分支 | `project-info search/detail`, `version-server list-versions`, `branch-server info` |
| 源码证据 | `opengrok search/fetch`, `gerrit search/get/files/diff` |
| workspace diff | `git repo-status`, `git repo-diff` |
| 编码规范 | `coding-standards checklist --language java --severity mandatory` |
| 模块编译 | `build native` |
| 提交 | `gerrit commit-message`, `gerrit create/upload` |

编排明细见 [`workflow.yaml`](../workflow.yaml)。

## 平台分流

- MTK 强特征：`MtkRIL`, `MtkSpnOverride`, `MtkServiceStateTracker`, `mt[0-9]+`
- QCOM 强特征：`QTIRILJ`, `QcomSpnOverride`, `QtiServiceStateTracker`, `sm[0-9]+`

只有公共 TAG 时不得定平台。分流后读：

- MTK：[mtk.md](mtk.md)
- QCOM：[qcom.md](qcom.md)

## 子 skill 链

```text
spn-workflow (本包)
  → spn-fault-analysis → qcom-spn-fault-analysis / mtk-spn-fault-analysis
  → spn-code-edit
  → spn-submit
```

## 交付物

- 分析：[report-template.md](report-template.md)
- 提交：[submission.md](submission.md)
