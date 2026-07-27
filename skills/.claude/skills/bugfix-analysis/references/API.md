# Bugfix AI API 参考（本 skill 已实现部分）

来源：[AI2D故障分析平台API接口文档 V1.0.0](https://transsioner.feishu.cn/wiki/EbtbwN3B5iRUGEkVTHLcXfExnrj)（**v1.1**，2026-07-22）

- **Base URL**: `https://chat.transsion.com/bugfix`
- **前缀**: `/api/v1`（网关）；应用内亦挂载 `/bugfix/api/v1`
- **认证**: `Authorization: Bearer <access_token>`（本 skill 可通过 `auth_required=false` 跳过）

## 结果 vs 过程

| 层级 | 结果 | 过程 |
|------|------|------|
| 落库 `analysis_task_records` | `analysis_markdown` | `process_markdown` / `process_messages` |
| 列表 `GET /analysis-task-records` | `analysis_markdown_preview` | **不含**完整 `process_*` |
| 详情 `GET /analysis-task-records/{id}` | `analysis_markdown` | `process_markdown` / `process_messages` |

列表里的 `agent_summary` **不等于**详情中的完整过程；查过程请用 `get-report`。

## 配置项

| 字段 | 默认 | 说明 |
|------|------|------|
| `auth_required` | `false` | `false` 跳过登录；`true` 启用 Bearer 认证 |
| `base_url` | `https://chat.transsion.com/bugfix` | API 根地址 |

## CLI ↔ API 映射

| CLI 命令 | HTTP | 路径 |
|----------|------|------|
| `login` | POST | `/api/v1/auth/login` |
| `login`（附带） | GET | `/api/v1/users/me` |
| `analyze` | POST | `/api/v1/jira-mcp/analyze` |
| `get-progress` | GET | `/api/v1/analysis-task-records` |
| `get-report` | GET | `/api/v1/analysis-task-records/{record_id}` |

## 1. 用户登录

```
POST /api/v1/auth/login
```

请求体：`username`、`password`（均必填）。

响应 200：`access_token`、`token_type`。

## 2. Jira 通用缺陷分析

```
POST /api/v1/jira-mcp/analyze
```

### 请求体（v1.1）

| 字段 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `jira_number` | 是 | — | Jira 工单号 |
| `gerrit_project` | 否 | `""` | 空则从工单关键词匹配 `module_repo_mapping` |
| `branch` | 否 | `""` | 分支名 |
| `keywords` | 否 | `""` | 英文逗号分隔，用于落库 mapping |
| `code_root_relative` | 否 | `""` | 代码子目录；空=整仓 |
| `auto_comment` | 否 | `true` | 是否写回 Jira |
| `skip_if_marker_present` | 否 | `true` | 已有标记评论则跳过 |
| `comment_marker` | 否 | `[AUTO-ANALYSIS]` | 去重标记 |
| `business_type` | 否 | `""` | `communication` / `stability` / `general` / `diruan` |

**已移除**：`skill_id_override`（当前请求模型不再支持）。

### 响应 200 主要字段

| 字段 | 说明 |
|------|------|
| `jira_number` / `gerrit_project` / `branch` | 实际使用的坐标 |
| `analysis_markdown` | **结果**报告 |
| `skill_id` | 使用的分析技能 |
| `clone_path` | 代码克隆/缓存路径 |
| `comment_added` / `comment_skipped_reason` | Jira 评论状态 |
| `opencode_request_id` | OpenCode 请求 ID |
| `opencode_prompt_tokens` / `opencode_completion_tokens` / `opencode_total_tokens` | Token 统计 |
| `mcp_failed` | 新链路恒为 `false`（兼容字段） |

建议超时 ≥ 600 秒。

## 3. 分析进展获取

```
GET /api/v1/analysis-task-records?jira_issue_key=...&preview_chars=...
```

Query 至少提供其一：`jira_issue_key`、`gerrit_project`、`gerrit_project_prefix`。

- `preview_chars`：0–8000，默认 500
- 列表项含 `analysis_markdown_preview`、`success`、`jira_error_type` 等
- **不含**完整 `process_*`

## 4. 分析报告获取

```
GET /api/v1/analysis-task-records/{record_id}
```

详情字段：

| 字段 | 说明 |
|------|------|
| `analysis_markdown` | **结果**终稿 |
| `process_markdown` | **过程**会话转 Markdown |
| `process_messages` | **过程**OpenCode session messages |
| `extra_json` | 扩展；常见 `process_source`、`process_incomplete`、`opencode_token_usage` |
| `success` / `error_message` / `comment_skipped_reason` | 状态与说明 |

## 通用错误

```json
{"detail": "错误描述信息"}
```
