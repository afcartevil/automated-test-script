# Jira CLI Reference

## CLI Base

From skill root (`jira-ops/`):

```bash
python scripts/api_jira.py <command> [options]
```

Optional: copy `.env.example` → `.env` for `FEISHU_*` and `NETWORK_SERVERS`.

## Log download channels

| Channel key | Source examples | Download method |
|-------------|-----------------|-----------------|
| `box` | `frbox.transsion.com`, `sgbox.transsion.com` | Aliyun PDS API → Playwright fallback |
| `feishu_file` | `*.feishu.cn/file/<token>` | Feishu OpenAPI (`FEISHU_APP_ID/SECRET`) |
| `network_share` | `\\10.x.x.x\share\...`, `Path:` lines | `net use` + file/dir copy (`NETWORK_SERVERS`) |
| `http_direct` | OSS `.zip`, fanslog HTTP | `requests` stream download |

Text scanned: **summary + description + all comments** (auto-export comment lines filtered).

## Commands

### list-log-sources

Classify URLs without downloading.

```bash
python scripts/api_jira.py list-log-sources --issue "OS162-37733"
```

`data.urls_by_type` keys: `box`, `feishu_file`, `network_share`, `http_direct`.

### download-logs

See prior doc. Add `--channels` to limit sources.

### extract-logs

Recursive decompression under one or more directories.

```bash
python scripts/api_jira.py extract-logs --input-dir "./jira_workspace/OS162-37733"
python scripts/api_jira.py extract-logs --input-dir "./a" --input-dir "./b" --no-recursive
```

Formats: zip, tar, tgz, gz, bz2, rar, 7z. RAR/7z need 7-Zip (`SEVEN_ZIP_EXE`).

`data.extracted_dirs` — log root directories after extraction.

### prepare-logs

Download all channels then extract (recommended).

```bash
python scripts/api_jira.py prepare-logs --issue "OS162-37733"
python scripts/api_jira.py prepare-logs --issue "OS162-37733" --output-dir "D:/work/OS162-37733"
```

### setup-check

```bash
python scripts/api_jira.py setup-check
```

Returns `data.ready` and per-item `checks[]` with `required` flag.

### env

```bash
python scripts/api_jira.py env show
python scripts/api_jira.py env set FEISHU_APP_ID=cli_xxx FEISHU_APP_SECRET=yyy
python scripts/api_jira.py env init-from-user --json '{"FEISHU_APP_ID":"cli_xxx"}'
```

`.env` path: `<skill-root>/.env`

### list-log-sources (legacy list-log-urls-from-description)

Same scan as `list-log-sources`; adds `log_http_urls` filter when `--all-urls` not set.

### copy-log-from-description (legacy)

Wraps `download-logs`. `--http-only` / `--unc-only` map to channel subsets.

## Other commands

See prior sections: `config`, `get-issue`, `add-comment`, `download-attachments`, `get-changelog`.

## Output contract

- Success: `{"ok": true, "data": ...}`
- Failure: `{"ok": false, "error": {"code": "...", "message": "..."}}`
