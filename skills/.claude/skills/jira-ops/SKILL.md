---
name: jira-ops
description: Use when user messages include a Jira issue ID (like ABC-123) or a Jira browse link and the user wants to query or update Jira data, download attachments, or download logs linked in the issue description (http/https or UNC).
---

# Jira CLI Operator Skill

## Purpose

Use local CLI wrappers in `scripts/api_jira.py` to operate Jira data and return tool output directly.

Supports:

- Jira issue query / comment / changelog / attachments
- **Logs in description**: `http(s)://` links (e.g. OSS fanslog `.zip`) and Windows `\\server\share\...` UNC paths

## Trigger

Apply this skill when the user provides:

- A Jira ID, such as `CM7OS16-418` or `X6873OS162-1079`
- A Jira link, such as `http://jira.transsion.com/browse/CM7OS16-418`

## Required Inputs

- Issue identifier (ID or browse URL)
- User intent (query, add comment, download attachments, **download logs from description**, list log URLs, view config)

## Cross-platform (Linux / Windows)

1. **Working directory**: Run all commands with the skill root as cwd (`jira-ops/`, the directory that contains `SKILL.md`).
2. **Python**: Use `python` (or `python3` on Linux if `python` is missing). Scripts use only stdlib + `jira` package.
3. **Install once** — prefer **bugtool** unified config (recommended):

   ```powershell
   bugtool --json config setup-jira --user "<user>" --password "<password>" --server "http://jira.transsion.com/"
   ```

   Or legacy from skill root:

   ```bash
   pip install -r requirements.txt
   python scripts/api_jira.py config set --server "http://jira.transsion.com/" --user "<user>" --password "<password>"
   ```

4. **Config file**: `~/.integration_bug_tool/env.yaml`（bugtool 主配置，自动同步到 `~/.jira_cli_config.json`）
5. **Jira 一键 case（推荐）**：`bugtool --json case open --issue "<url>"` — 取单、下日志、写 `case_manifest.json` 并推荐分析 skill。

6. **Shell wrappers** (optional, same args as `api_jira.py`):
   - Linux/macOS: `bash scripts/deploy.sh <command> ...`
   - Windows PowerShell: `.\scripts\deploy.ps1 <command> ...`
7. **PowerShell**: Chain commands with `;`, not `&&`.
7. **UNC paths**: Only work when the share is reachable on that machine (typical on corp Windows). On Linux, prefer `--http-only` for OSS/http log links.

## Execution Rules

1. Run commands from the `jira-ops` skill directory (see paths below).
2. Prefer direct command mapping from intent to one CLI command.
3. Return the command output JSON directly to user (no schema rewrite).
4. If command fails, return the error JSON directly.
5. For log download, prefer `list-log-urls-from-description` first when the user only needs URLs; use `copy-log-from-description` to download.

## Command paths

Use **one** of these (from skill root):

| Platform | Command prefix |
|----------|----------------|
| Any | `python scripts/api_jira.py` |
| Linux/macOS | `bash scripts/deploy.sh` |
| Windows | `.\scripts\deploy.ps1` |

Examples below use `python scripts/api_jira.py`.

## Command Mapping

- **Show config**
  - `python scripts/api_jira.py config show`
- **Set config**
  - `python scripts/api_jira.py config set --server "<server>" --user "<user>" --password "<password>"`
- **Get issue details**
  - `python scripts/api_jira.py get-issue --issue "<jira-id-or-url>"`
- **Add comment**
  - `python scripts/api_jira.py add-comment --issue "<jira-id-or-url>" --comment "<comment>"`
- **Download attachments**
  - `python scripts/api_jira.py download-attachments --issue "<jira-id-or-url>" --output-dir "<dir-optional>"`
- **Get changelog**
  - `python scripts/api_jira.py get-changelog --issue "<jira-id-or-url>"`
- **List log URLs in description** (no download)
  - `python scripts/api_jira.py list-log-urls-from-description --issue "<jira-id-or-url>"`
  - Include images/other links: add `--all-urls`
- **Download logs from description** (http(s) + optional UNC)
  - `python scripts/api_jira.py copy-log-from-description --issue "<jira-id-or-url>" --output-dir "<dir-optional>"`
  - OSS/http only: `--http-only`
  - UNC only: `--unc-only`
  - Also download non-log URLs (e.g. pictures): `--all-urls`

### Example: fans feedback issue with OSS zip links

```bash
python scripts/api_jira.py list-log-urls-from-description --issue "http://jira.transsion.com/browse/X6873OS162-1079"
python scripts/api_jira.py copy-log-from-description --issue "X6873OS162-1079" --output-dir "./jira_logs" --http-only
```

## Utility Files

- Script runner (bash): `scripts/deploy.sh`
- Script runner (PowerShell): `scripts/deploy.ps1`
- Validation helper: `scripts/validate.py`
- Reference details: `references/REFERENCE.md`
- Config template: `assets/config-template.json`
- Dependencies: `requirements.txt`
