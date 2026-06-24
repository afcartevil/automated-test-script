# 运行模式

| 模式 | 日志准备 (`log-pipeline`) | 分析 (L0~L3) | 飞书看板 |
|------|--------------------------|-----------------|----------|
| full | 执行 | 执行 | 仅用户要求时 |
| prepare-only | 执行 | 跳过 | 无 |
| analyze-only | 跳过（要求已有 manifest） | 执行 | 仅用户要求时 |
| manifest | 跳过 | 执行（显式 `manifest_path`） | 仅用户要求时 |

## 用户话术 → 模式

| 话术 | 模式 |
|------|------|
| 分析某 Jira 单 / 一条龙 | full |
| 只下载 log / 只准备日志 | prepare-only |
| log 已经有了 / 直接分析 | analyze-only |
| 分析这个 manifest / 指定路径 | manifest |

## analyze-only 前置检查

- `{WORKSPACE_ROOT}/{issue_key}/job_manifest.json` 存在且可解析
- `issue_key` 与 manifest 内一致
- 不满足时建议改 **full** 或让用户指定 **manifest** 绝对路径
