---
name: loginsight-remote-cli
description: >-
  Call a deployed LogInsight instance via CLI for model/account config, Jira
  analysis start, progress polling, and report download. Use when the user
  wants remote LogInsight analysis against chat.transsion.com or another
  deployed base URL, or asks to drive Jira analysis / status / report over HTTP.
---

# LogInsight Remote CLI

对**已部署**的 LogInsight（默认 `https://chat.transsion.com/bugfix/stability-matrix-tools`）发起 HTTP 调用。

```bash
cd .cursor/skills/loginsight-remote-cli
python scripts/loginsight_cli.py <command> [options]
```

Python 3.10+ 标准库即可。

---

## Agent 强制流程

### Step 0 — doctor

```bash
python scripts/loginsight_cli.py doctor
```

`ok=false` 时按 `checks` 缺项进入 Step 1。

### Step 1 — 一次性写入本地状态（之后不必再配）

**没有**「查询某操作者是否已在服务器配置 Key」的专用 API。  
`GET /api/ai/config/overview` 只反映平台 YAML / `_legacy` 池。  
因此凭据以**本地 gitignore 文件**为事实源：

| 文件 | 内容 |
|------|------|
| `.loginsight_cli.json` | base_url / operator / llm key |
| `.env` | 同上（便于人读） |

二者已在 skill 内 `.gitignore`，且仓库根 `.gitignore` 忽略整个 `.cursor/skills/`。

首次（或用户改密/换 Key）执行：

```bash
python scripts/loginsight_cli.py config set \
  --operator-user "<用户名>" \
  --operator-password "<密码>"

python scripts/loginsight_cli.py credentials set \
  --provider-key sw-aimodel \
  --api-key "<LLM_API_KEY>"
```

查看本地是否就绪：

```bash
python scripts/loginsight_cli.py credentials status
```

### Step 2 — 一键分析（推荐）

本地已有 user/pass/key 后，**直接**：

```bash
python scripts/loginsight_cli.py run-jira --jira-id TOS163-5298 --force-reanalyze --out-dir ./out
```

CLI 会自动把本地 `LLM_API_KEY` 注入请求体 `llmApiKey`（优先级高于服务器欠费的平台 Key）。

若 `report_download_ok=false` 但 `result.success=true`（常见 nginx **504**），用返回的 `report.browser_url` 在浏览器打开报告即可。

### Step 3 — 分步命令

| 目的 | 命令 |
|------|------|
| 本地凭据状态 | `credentials status` |
| 保存/同步 Key | `credentials set --api-key ...` |
| 模型概览（平台侧） | `model overview` |
| Jira 连通 | `account jira-test` |
| 启动分析 | `analyze-jira --jira-id KEY [--force-reanalyze]` |
| 轮询 | `wait --task-id <id>` |
| 下报告 | `report --task-id <id> --out-dir ./out` |

详见 [reference.md](reference.md)。

---

## 行为约束

1. Linux 服务器模式：请求须带操作者 user+password；LLM 提供方固定 `sw-aimodel`。
2. **分析请求必须带本地 `llmApiKey`**（由 CLI 自动注入），避免落到平台欠费 Key。
3. 勿在对话中回显完整密码/API Key；只用 `credentials status` 的 masked 字段。
4. 密钥文件禁止提交 Git。

---

## 向用户索取信息（仅首次）

```text
1. OPERATOR_USER
2. OPERATOR_PASSWORD
3. LLM_API_KEY（算力平台 Key；provider 默认 sw-aimodel）
4. JIRA_ID
5. force-reanalyze: true/false（要真跑分析建议 true）
```
