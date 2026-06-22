# Jira CLI Reference

## CLI Base

From skill root (`jira-ops/`):

```bash
python scripts/api_jira.py <command> [options]
```

## Commands

### 1) config show

Show current Jira config with masked password.

```bash
python scripts/api_jira.py config show
```

### 2) config set

Set Jira server, username, password.

```bash
python scripts/api_jira.py config set --server "http://jira.transsion.com/" --user "qing.li3" --password "******"
```

### 3) get-issue

Get issue title, description, comments.

```bash
python scripts/api_jira.py get-issue --issue "CM7OS16-418"
```

### 4) add-comment

Add a comment to one issue.

```bash
python scripts/api_jira.py add-comment --issue "CM7OS16-418" --comment "comment text"
```

### 5) download-attachments

Download issue attachments to local path.

```bash
python scripts/api_jira.py download-attachments --issue "CM7OS16-418" --output-dir "./jira_attachments"
```

### 6) get-changelog

Get issue changelog entries.

```bash
python scripts/api_jira.py get-changelog --issue "CM7OS16-418"
```

### 7) list-log-urls-from-description

Parse log-related `http(s)` URLs and UNC paths from description without downloading.

```bash
python scripts/api_jira.py list-log-urls-from-description --issue "X6873OS162-1079"
python scripts/api_jira.py list-log-urls-from-description --issue "X6873OS162-1079" --all-urls
```

Response `data` fields:

- `http_urls`: all http(s) links found
- `log_http_urls`: filtered log-like links (`.zip`, `fanslog`, `TagLog`, etc.; excludes `.jpg`/`.png`)
- `unc_paths`: `\\server\share\...` paths

### 8) copy-log-from-description

Download log `http(s)` links and/or copy UNC directory contents to local path.

```bash
# OSS / http log zips (fans feedback style)
python scripts/api_jira.py copy-log-from-description --issue "X6873OS162-1079" --output-dir "./jira_logs" --http-only

# Legacy UNC share copy (Windows, share must be reachable)
python scripts/api_jira.py copy-log-from-description --issue "CM7OS16-418" --output-dir "./jira_logs" --unc-only

# Both when present
python scripts/api_jira.py copy-log-from-description --issue "CM7OS16-418" --output-dir "./jira_logs"
```

Options:

| Flag | Meaning |
|------|---------|
| `--output-dir` | Target directory (default: `./jira_attachments`) |
| `--http-only` | Skip UNC copy |
| `--unc-only` | Skip http download |
| `--all-urls` | Download all http links, not only log-like |
| `--timeout` | Per-file http timeout seconds (default 300) |

## Output Contract

- Return command output JSON directly.
- Success shape: `{"ok": true, "data": ...}`
- Failure shape: `{"ok": false, "error": {"code": "...", "message": "..."}}`
