---
name: bugfix-analysis
description: >-
  通过 CLI 调用 Bugfix AI 分析平台（chat.transsion.com/bugfix API v1.1）完成 Jira
  缺陷 AI 分析：登录（可关闭）、触发通用缺陷分析、查询分析进展、获取分析报告与过程。
  当用户要 AI 分析问题单、Bugfix 分析、Jira MCP 分析、远程缺陷分析、或提到 Bugfix
  AI 平台时使用。
---

# Bugfix AI 问题分析

对接 [Bugfix AI 分析平台 API v1.1](https://transsioner.feishu.cn/wiki/EbtbwN3B5iRUGEkVTHLcXfExnrj)（Base URL: `https://chat.transsion.com/bugfix`，前缀 `/api/v1`）。

与 `jira-ops` 的边界：`jira-ops` 直连 Jira 查单/下日志；**本 skill 调用 Bugfix 平台做 AI 代码分析**。

## 结果 vs 过程（v1.1 重要语义）

| 内容 | 字段 | 从哪里取 |
|------|------|----------|
| **分析结果**（终稿） | `analysis_markdown` | `analyze` 响应 / `get-report` |
| **分析过程**（会话） | `process_markdown`、`process_messages` | **仅** `get-report` 详情 |
| **进展预览** | `analysis_markdown_preview` | `get-progress` 列表 |

`get-progress` 列表**不含**完整过程；需要过程时必须 `get-report --record-id <id>`。

## 工作目录

所有命令在 **本 skill 根目录**（`bugfix-analysis/`）执行。

| 平台 | 命令前缀 |
|------|----------|
| 任意 | `python scripts/api_bugfix.py` |
| Windows | `.\scripts\deploy.ps1` |
| Linux/macOS | `bash scripts/deploy.sh` |

## 认证开关（`auth_required`）

| 值 | 行为 |
|----|------|
| `false`（**当前默认**） | 跳过登录，直接调 API |
| `true` | 须 `config set` + `login`，自动复用 token |

```bash
python scripts/api_bugfix.py config show
python scripts/api_bugfix.py config set --auth-required true --username "<用户>" --password "<密码>"
python scripts/api_bugfix.py login
```

## 标准工作流

```
- [ ] 0. config show 确认 auth_required
- [ ] 1. auth_required=true 时：login
- [ ] 2. 收集 jira_number（必填）；gerrit_project / branch 可选（v1.1 可省略由平台匹配）
- [ ] 3. analyze 触发分析（同步，timeout ≥ 600s）
- [ ] 4. get-progress 查记录列表与预览
- [ ] 5. get-report 取完整结果 + 过程
- [ ] 6. 向用户呈现 analysis_markdown；需要过程时一并展示 process_markdown
```

### 1. 用户登录（仅 `auth_required=true`）

```bash
python scripts/api_bugfix.py login
```

API：`POST /api/v1/auth/login`

### 2. Jira 通用缺陷分析

API：`POST /api/v1/jira-mcp/analyze`

**必填**：`--jira-number`

**可选**（v1.1）：`--gerrit-project` 省略时服务端按工单关键词匹配仓库；`--branch` 省略传空由服务端决定。

```bash
# 仅 Jira 单号（平台自动匹配仓库）
python scripts/api_bugfix.py analyze \
  --jira-number "TOS163-42648" \
  --auto-comment false \
  --timeout 600 \
  --output-file "./TOS163-42648-analysis.md"

# 指定仓库与业务类型
python scripts/api_bugfix.py analyze \
  --jira-number "TOS163-123" \
  --gerrit-project "TRAN_CODE/App/TranSystemServer" \
  --branch "master" \
  --business-type "diruan" \
  --keywords "TranSystemServer,framework" \
  --timeout 600
```

| CLI 参数 | API 字段 | 说明 |
|----------|----------|------|
| `--jira-number` | `jira_number` | **必填** |
| `--gerrit-project` | `gerrit_project` | 可选；空则关键词匹配 |
| `--branch` | `branch` | 可选 |
| `--keywords` | `keywords` | 英文逗号分隔 |
| `--business-type` | `business_type` | `communication`/`stability`/`general`/`diruan` |
| `--code-root-relative` | `code_root_relative` | 代码子目录 |
| `--auto-comment` | `auto_comment` | 默认 true |
| `--skip-if-marker-present` | `skip_if_marker_present` | 默认 true |
| `--comment-marker` | `comment_marker` | 默认 `[AUTO-ANALYSIS]` |
| `--timeout` | — | 默认 600 秒 |
| `--output-file` | — | 保存 `analysis_markdown` |

**已移除**（v1.1 不再支持）：`--skill-id-override` / `skill_id_override`。

响应 `data.response` 新增：`jira_number`、`gerrit_project`、`branch`、`opencode_*_tokens`；`mcp_failed` 新链路恒为 `false`。

### 3. 分析进展获取

API：`GET /api/v1/analysis-task-records`

```bash
python scripts/api_bugfix.py get-progress --jira-issue-key "TOS163-42648"
python scripts/api_bugfix.py get-progress --jira-issue-key "TOS163-42648" --preview-chars 800
```

返回列表含 `analysis_markdown_preview`（默认预览 500 字符）。从 `items[].id` 取 `record_id`。

### 4. 分析报告获取

API：`GET /api/v1/analysis-task-records/{record_id}`

```bash
python scripts/api_bugfix.py get-report --record-id 8035 \
  --output-file "./TOS163-42648-result.md" \
  --output-process-file "./TOS163-42648-process.md"
```

- `--output-file` → `analysis_markdown`（**结果**）
- `--output-process-file` → `process_markdown`（**过程**）

## 执行规则

1. `auth_required=false` 时跳过 login。
2. **优先只传 Jira 单号**；用户未给仓库时不要强行编造 `gerrit_project`。
3. 需要完整过程时必须 `get-report`，不要只靠 `get-progress` 列表。
4. 直接返回 CLI JSON，不改写 schema。
5. 默认 `auto_comment=true`；用户未要求回写 Jira 时传 `--auto-comment false`。

## 典型场景

**场景 A — 只给 Jira 单号**

```bash
python scripts/api_bugfix.py analyze \
  --jira-number "TOS163-42648" \
  --auto-comment false \
  --timeout 600 \
  --output-file "./TOS163-42648-analysis.md"
```

**场景 B — 查进展并取完整报告+过程**

```bash
python scripts/api_bugfix.py get-progress --jira-issue-key "TOS163-42648"
python scripts/api_bugfix.py get-report --record-id <items[0].id> \
  --output-file "./result.md" --output-process-file "./process.md"
```

## 异常引导

| 现象 | 处理 |
|------|------|
| `AUTH_DISABLED` | `auth_required=false`，无需 login |
| HTTP 401 | `login` 或检查 `auth_required` |
| HTTP 403 | 账号缺 `admin:all` 或 `module:analyze`（进展/报告接口） |
| analyze 500 + clone 403 | 平台 Gerrit 权限问题；或省略 `--gerrit-project` 让平台自动匹配 |
| analyze 500 + issue_type=unknown | 不传仓库且平台无法匹配 mapping |
| analyze 超时 | 增大 `--timeout`（≥ 600） |

## 依赖

- Python 3.8+（标准库）
- 网络可达 `https://chat.transsion.com/bugfix`

## 参考

- 字段速查：[references/API.md](references/API.md)
