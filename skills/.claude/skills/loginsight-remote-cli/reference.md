# LogInsight Remote CLI — API notes

## Base URL

`https://chat.transsion.com/bugfix/stability-matrix-tools` (no trailing slash)

## Auth / keys

- No JWT. Linux analysis needs `jiraUsername` + `jiraPassword` on each start body.
- **No API** returns “keys configured for operator X”.
  - Closest: `GET /api/ai/config/overview` → `providers[].hasKey` for YAML/`_legacy` pool only.
- CLI local state (gitignored): `.env` + `.loginsight_cli.json` hold operator + `LLM_API_KEY`.
- On `analyze-jira` / `run-jira`, CLI injects `llmApiKey` / `llmApiKeys` from local state (beats platform YAML key).

## Endpoint map (CLI ↔ HTTP)

| CLI | HTTP |
|-----|------|
| `credentials status` | local files + `GET /api/ai/config/overview` (platform only) |
| `credentials set` | write local; optional `POST /api/ai/credentials/sync` |
| `credentials sync` | `POST /api/ai/credentials/sync` + local save |
| `model providers` | `GET /api/ai/providers` |
| `model overview` | `GET /api/ai/config/overview` |
| `model keys` | `POST /api/ai/config/providers/keys` |
| `model scene-bind` | `PUT /api/ai/config/scene-bindings` |
| `account jira-test` | `POST /api/jira/test-connection` |
| `analyze-jira` | `POST /api/analysis/jira/start` → 202 `{taskId}` |
| `status` / `wait` | `GET /api/analysis/status?taskId=` |
| `report` | `GET /api/reports/file?path=` |

## analyze-jira body (with personal key)

```json
{
  "jiraUsername": "<operator>",
  "jiraPassword": "<non-empty>",
  "jiraIds": ["TOS163-5298"],
  "llmProvider": "sw-aimodel",
  "llmApiKey": "<from local state>",
  "llmApiKeys": ["<from local state>"],
  "forceReanalyze": true
}
```

## status fields

- `status`: `running` | `done` | `not_found`
- `result.success`, `result.message`, `result.resultPath`, `result.failureCode`

## Common failures

| Symptom | Likely cause |
|---------|----------------|
| `LLM_INSUFFICIENT_QUOTA` without local key | Platform YAML key exhausted — run `credentials set` |
| `请先在凭据栏填写操作者用户名和密码` | Missing local operator user/password |
| `no resultPath` | Analysis failed; read `result.message` |
