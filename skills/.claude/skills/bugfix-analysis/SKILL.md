---
name: bugfix-analysis
description: >-
  通过 CLI 调用 Bugfix 故障分析核心 API（三接口）：问题分析、分析过程、报告获取。
  当用户要 AI 分析问题单、Bugfix 分析、Jira MCP 分析、远程缺陷分析、或提到 Bugfix
  AI 平台时使用。
---

# Bugfix 故障分析（核心三接口）

对接 [故障分析核心 API](https://transsioner.feishu.cn/wiki/ZNlYwLZBWi3dD1kwKUUcmCTInVb)  
Base：`https://chat.transsion.com/bugfix`，前缀 `/api/v1`

| 能力 | CLI | API |
|------|-----|-----|
| 问题分析 | `analyze` | `POST /jira-mcp/analyze` |
| 分析过程 | `get-report`（`process_*`） | `GET /analysis-task-records/{id}` |
| 报告获取 | `get-report`（`analysis_markdown`） | 同上（先 `get-progress` 拿 id） |

与 `jira-ops` 边界：那边直连 Jira；**本 skill 调 Bugfix 平台做 AI 分析**。

## 工作目录

在 skill 根目录（`bugfix-analysis/`）执行：

| 平台 | 命令前缀 |
|------|----------|
| 任意 | `python scripts/api_bugfix.py` |
| Windows | `.\scripts\deploy.ps1` |
| Linux/macOS | `bash scripts/deploy.sh` |

## 鉴权说明

| 接口 | 鉴权 |
|------|------|
| `analyze` | **当前无需 JWT**（始终裸调） |
| `get-progress` / `get-report` | 文档要求 Bearer（`admin:all` 或 `module:analyze`） |

若过程/报告返回 401/403：

```bash
python scripts/api_bugfix.py config set --auth-required true --username "<用户>" --password "<密码>"
python scripts/api_bugfix.py login
```

## 推荐对接流程

```
1. analyze --jira-number ... --business-type ...  → 同步拿 analysis_markdown
2. get-progress --jira-issue-key ...               → 拿 items[].id
3. get-report --record-id ...                      → analysis_markdown=报告，process_markdown=过程
```

## 1. 问题分析

**必填**：`--jira-number`、`--business-type`

```bash
python scripts/api_bugfix.py analyze \
  --jira-number "BUG-12345" \
  --business-type "stability" \
  --auto-comment false \
  --timeout 600 \
  --output-file "./BUG-12345-analysis.md"
```

| CLI | API | 必填 | 说明 |
|-----|-----|------|------|
| `--jira-number` | `jira_number` | 是 | 工单号 |
| `--business-type` | `business_type` | **是** | `communication` / `stability` / `general` / `diruan` |
| `--gerrit-project` | `gerrit_project` | 否 | 空则按工单关键词自动匹配 |
| `--branch` | `branch` | 否 | |
| `--keywords` | `keywords` | 否 | 逗号分隔 |
| `--auto-comment` | `auto_comment` | 否 | 默认 true |
| `--skip-if-marker-present` | `skip_if_marker_present` | 否 | 默认 true |
| `--comment-marker` | `comment_marker` | 否 | 默认 `[AUTO-ANALYSIS]` |
| `--timeout` | — | 否 | 默认 600 |
| `--output-file` | — | 否 | 保存报告 |

响应含 `analysis_markdown`（报告）。**同步响应不含过程**。

## 2. 查记录 ID（进展列表）

```bash
python scripts/api_bugfix.py get-progress --jira-issue-key "BUG-12345"
```

可选：`--gerrit-project` / `--gerrit-project-prefix`（三选一至少一个）、`--page-num`、`--page-size`。

列表只有预览，**不含**完整过程；从 `items[].id` 取 `record_id`。

## 3. 报告 + 过程（详情）

```bash
python scripts/api_bugfix.py get-report --record-id 1001 \
  --output-file "./result.md" \
  --output-process-file "./process.md"
```

| 字段 | 用途 |
|------|------|
| `analysis_markdown` | **报告** |
| `process_markdown` / `process_messages` | **过程** |
| `success` / `skipped` / `error_message` | 状态 |
| `jira_error_type` | 0未知 1ANR 2JE 3SWT 4KE |

## 执行规则

1. `analyze` **必须**带 `--business-type`；用户未给时先问，勿猜。
2. 用户未给仓库时不要编造 `gerrit_project`。
3. 需要过程时必须 `get-report`，不要只靠 `get-progress`。
4. 直接返回 CLI JSON；用户未要求回写 Jira 时传 `--auto-comment false`。

## 异常引导

| 现象 | 处理 |
|------|------|
| 缺少 `business_type` | 停止，请用户指定四选一 |
| `AUTH_REQUIRED_FOR_RECORDS` | `config set --auth-required true` + `login` |
| analyze 500 + issue_type=unknown | 平台无法匹配仓库，补 `gerrit_project`/`keywords` |
| analyze 超时 | 增大 `--timeout`（≥ 600） |

## 参考

- [references/API.md](references/API.md)
