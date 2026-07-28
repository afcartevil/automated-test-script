# 故障分析核心 API（本 skill 已实现）

来源：[故障分析核心 API](https://transsioner.feishu.cn/wiki/ZNlYwLZBWi3dD1kwKUUcmCTInVb)

- **Base**：`https://chat.transsion.com/bugfix`
- **前缀**：`/api/v1`（亦支持 `/bugfix/api/v1`）
- **格式**：`application/json`

## 三接口总览

| 能力 | 接口 | 关键字段 |
|------|------|----------|
| 问题分析 | `POST /jira-mcp/analyze` | 触发分析，同步返回报告 |
| 分析过程 | `GET /analysis-task-records/{id}` | `process_markdown` / `process_messages` |
| 报告获取 | `GET /analysis-task-records/{id}` | `analysis_markdown` |

过程与报告在同一详情接口；先列表拿 `id`，再查详情。

## CLI ↔ API

| CLI | HTTP | 路径 | 鉴权 |
|-----|------|------|------|
| `analyze` | POST | `/api/v1/jira-mcp/analyze` | **当前无需 JWT** |
| `get-progress` | GET | `/api/v1/analysis-task-records` | Bearer（`admin:all` / `module:analyze`） |
| `get-report` | GET | `/api/v1/analysis-task-records/{id}` | 同上 |
| `login` | POST | `/api/v1/auth/login` | 否（仅 records 需要时启用） |

## 1. 问题分析

```
POST /api/v1/jira-mcp/analyze
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `jira_number` | string | 是 | 工单号 |
| `business_type` | string | **是** | `communication` / `stability` / `general` / `diruan` |
| `gerrit_project` | string | 否 | 空则按工单关键词自动匹配 |
| `branch` | string | 否 | |
| `keywords` | string | 否 | 逗号分隔 |
| `auto_comment` | bool | 否 | 默认 true |
| `skip_if_marker_present` | bool | 否 | 默认 true |
| `comment_marker` | string | 否 | 默认 `[AUTO-ANALYSIS]` |

**相对旧版变更**：`business_type` 从可选改为**必填**；文档不再包含 `code_root_relative` / `skill_id_override`。

响应节选：`analysis_markdown`、`jira_number` / `gerrit_project` / `branch` / `skill_id`、`comment_added` / `comment_skipped_reason`、`mcp_failed`。

同步响应**不含**分析过程。

```bash
curl -X POST "https://chat.transsion.com/bugfix/api/v1/jira-mcp/analyze" \
  -H "Content-Type: application/json" \
  -d '{"jira_number":"BUG-12345","business_type":"stability"}'
```

## 2. 分析过程 / 3. 报告获取

### Step 1 — 按工单查记录 ID

```
GET /api/v1/analysis-task-records?jira_issue_key={工单号}
```

Query 三选一至少一个：`jira_issue_key` / `gerrit_project` / `gerrit_project_prefix`。  
可选：`page_num`（默认 1）、`page_size`（默认 20）。

响应 `items[].id` = `record_id`。列表只有报告预览，不含完整过程。

### Step 2 — 详情

```
GET /api/v1/analysis-task-records/{record_id}
```

| 字段 | 用途 |
|------|------|
| `analysis_markdown` | **报告** |
| `process_markdown` | **过程**（会话转 Markdown） |
| `process_messages` | **过程**（OpenCode 原始 messages） |
| `success` / `skipped` / `error_message` | 状态 |
| `jira_error_type` | `0`未知 `1`ANR `2`JE `3`SWT `4`KE |

## 推荐对接流程

```
1. POST /jira-mcp/analyze
2. GET  /analysis-task-records?jira_issue_key=...
3. GET  /analysis-task-records/{id}
      → analysis_markdown = 报告
      → process_markdown  = 过程
```

## 错误

```json
{"detail":"..."}
```

常见码：`200` / `400` / `401` / `403` / `404` / `500`。
