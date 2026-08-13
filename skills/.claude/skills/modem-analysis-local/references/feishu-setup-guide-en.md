# modem-analysis-local — Setup & Usage Guide (English)

> Skill version 1.0.0 · Windows local log preparation + L0→L3 AI modem fault analysis  
> 中文版: [Feishu doc](https://transsioner.feishu.cn/docx/RwFgdfxt8oufDsxhg0Sc0g84nQg) · `references/feishu-setup-guide.md`

## Overview

`modem-analysis-local` is a **Cursor Agent Skill** that runs on your machine:

- **Log preparation** (`log-pipeline/`): Jira issue → download → extract → trace export → `job_manifest.json`
- **Layered analysis** (`analysis_skills/`): L0 baseline → L1 business judgment → L2 domain analysis → L3 final conclusion
- **Optional scripts** (`scripts/`): manifest updates, optional Feishu dashboard sync

**Skill root (`SKILL_ROOT`)**: the directory containing `SKILL.md`. Run all commands below from that directory.

---

## 1. Python environment setup

### 1.1 Prerequisites

- **Python 3.9+** (3.10 or 3.11 recommended)
- **Windows** (the log pipeline is primarily tested on Windows)
- **Disk space**: one issue workspace can use several GB. Set `WORKSPACE_ROOT` on a **local SSD** (e.g. `D:\` or `E:\`). Do not point it directly at a UNC network path.

### 1.2 Install the skill in Cursor

Place the `modem-analysis-local/` folder in one of:

| Scope | Example path |
|-------|----------------|
| Project | `<project>/.cursor/skills/modem-analysis-local/` |
| Global | `~/.cursor/skills/modem-analysis-local/` |

In this repo: `<project>/.agents/skills/modem-analysis-local/`

### 1.3 Create a virtual environment and install dependencies

From **skill root**:

```powershell
cd <SKILL_ROOT>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Main packages in `requirements.txt`:

| Package | Purpose |
|---------|---------|
| `requests`, `python-dotenv` | HTTP / environment variables |
| `jira`, `pygerrit2` | Jira / Gerrit (log pipeline) |
| `jsonschema` | `job_manifest.json` validation |

### 1.4 Optional Python dependencies

| Scenario | Action |
|----------|--------|
| **Box cloud browser download** | Uncomment `playwright` in `requirements.txt`, then `python -m playwright install chromium` |
| **finalize NAS upload (no system smbclient)** | Uncomment `smbprotocol` and `pip install` |
| **Environment self-check** | `python log-pipeline\_shared\check_environment.py` (if present) |

### 1.5 External tools (log export, as needed)

| Tool | Environment variable | Purpose |
|------|----------------------|---------|
| 7-Zip | `SEVEN_ZIP_EXE` | Extract rar/7z |
| ELT / NLT | `ELT_HOME`, `NLT_HOME` | MTK trace export |
| Wireshark | `WIRESHARK_PATH` | PCAP → txt |
| Qualcomm QUTS | `QUTS_PYTHON_PATH` | QCOM diag export |

See `references/setup.md` inside the skill for more detail.

---

## 2. `.env` configuration

### 2.1 Two `.env` files — keep them in sync

Two files are used; **keep them aligned** (at minimum `WORKSPACE_ROOT`, Jira settings, and tool paths):

| File | Read by |
|------|---------|
| `<SKILL_ROOT>/.env` | Analysis layer and some scripts |
| `<SKILL_ROOT>/log-pipeline/.env` | `run_pipeline.py` and pipeline steps |

**Recommended workflow:**

```powershell
cd <SKILL_ROOT>
copy .env.example .env
# Edit .env and fill required values
copy .env log-pipeline\.env
```

For advanced pipeline options (Samba publish, Jira watcher, Gerrit, etc.), refer to `log-pipeline/.env.example` and add variables to `log-pipeline/.env` without conflicting with the root `.env`.

### 2.2 Required variables

| Variable | Description | Example |
|----------|-------------|---------|
| `WORKSPACE_ROOT` | Local workspace root; output `{WORKSPACE_ROOT}/{issue_key}/job_manifest.json` | `D:\modem_workspace` |
| `JIRA_SERVER` | Jira API base URL | `http://jira.transsion.com` |
| `JIRA_USERNAME` | Jira account | — |
| `JIRA_PASSWORD` | Jira password or API token | — |

### 2.3 Common optional variables (log export / local pipeline)

| Variable | Description |
|----------|-------------|
| `SEVEN_ZIP_EXE` | Path to 7-Zip executable |
| `WIRESHARK_PATH` | Wireshark install directory |
| `ELT_HOME` / `NLT_HOME` | MTK export tool roots |
| `QUTS_PYTHON_PATH` | QUTS bundled Python (QCOM export) |
| `SMB_PUBLISH_ENABLED` | `0` = local analysis only, no Samba upload; `1` = publish zip after pipeline |

### 2.4 Feishu / Lark (**usually not required**)

This skill is for **local Cursor analysis**. In most cases you **do not need** the variables below—leave them empty or commented out:

| Variable | Purpose | Needed for local analysis? |
|----------|---------|----------------------------|
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | Feishu file download, L2-EE history, dashboard upsert | Usually **no** |
| `FEISHU_DASHBOARD_APP_TOKEN` / `FEISHU_DASHBOARD_TABLE_ID` | Analysis dashboard Bitable | Usually **no** |
| `FEISHU_DASHBOARD_ENABLED` | Pipeline Step 10 write to dashboard | Usually **no** |
| `JIRA_BROWSE_URL_BASE` | Jira link display on dashboard only | **no** if you skip dashboard |

Configure only when your team explicitly needs dashboard sync, EE history lookup, or Feishu attachments. See the Feishu section in `log-pipeline/.env.example`.

### 2.5 Gerrit (optional)

Used by pipeline steps such as `fetch_mddb_for_logs.py` for change lookup. **Leave blank if you do not need MDDB / patch correlation.**

| Variable | Description | Example |
|----------|-------------|---------|
| `GERRIT_URL` | Gerrit host | `https://gerrit.transsion.com` |
| `GERRIT_USERNAME` | Your Gerrit account | — |
| `GERRIT_PASSWORD` | Password or HTTP access token | — |

```ini
# ----- Gerrit (optional) -----
GERRIT_URL=https://gerrit.transsion.com
GERRIT_USERNAME=
GERRIT_PASSWORD=
```

Sync the same values to `log-pipeline\.env`.

### 2.6 `NETWORK_SERVERS` (recommended when Jira has UNC log paths)

`download_box_logs.py` uses this JSON list to resolve and access **`\\server\share\...`** paths in Jira comments/descriptions. If logs are only on Box/HTTP links, use `[]` or omit.

**Format**: single-line JSON array; each object has `server`, `share`, `username`, `password` (multiple servers = multiple objects).

```ini
# ----- Network shares (UNC paths for download_box_logs.py) -----
NETWORK_SERVERS=[{"server":"10.205.101.200","share":"fans_log","username":"<user>","password":"<pass>"},{"server":"10.150.152.37","share":"fans_log","username":"<user>","password":"<pass>"}]
```

Notes:

- You may copy the default fan-log server list from `log-pipeline/.env.example`; **do not commit real credentials** or paste them into shared docs
- After edits: `copy .env log-pipeline\.env`

### 2.7 Other pipeline extensions (`log-pipeline/.env.example`)

For full automation / publish flows only, e.g.:

- `SMB_*` — Samba publish target and credentials
- `QCOM_*` — Qualcomm export flags
- `JIRA_EXPORT_WATCHER_*` — Jira polling auto-export

### 2.8 Security

- **Do not commit `.env` to Git.** Do not ship `.env` or issue data under `WORKSPACE_ROOT` when sharing the skill.
- Use placeholders in docs; never paste real credentials.

---

## 3. Usage

### 3.1 Natural-language prompts to Cursor Agent

| Mode | Example user prompt | Agent behavior |
|------|----------------------|----------------|
| **full** | “Analyze OS162-37733” | Log prep + L0→L3 + report |
| **prepare-only** | “Only download and prepare logs for OS162-37733” | Run pipeline only; return manifest path |
| **analyze-only** | “Logs are ready, analyze OS162-37733 directly” | Skip pipeline; start at L0 |
| **manifest** | “Analyze this manifest” + path | Use given `job_manifest.json` |

### 3.2 Manual log preparation (Step 0)

```powershell
cd <SKILL_ROOT>
$env:PYTHONIOENCODING = "utf-8"
python log-pipeline\run_pipeline.py --issue-key <ISSUE_KEY>
```

On success, manifest is written to:

```text
{WORKSPACE_ROOT}/{issue_key}/job_manifest.json
```

On failure, inspect pipeline output (Jira, download, extract, export tools, etc.).

### 3.3 AI analysis flow (Steps 1–4)

The Agent reads and follows each layer’s `SKILL.md` in order (**AI performs analysis; do not run layer `scripts/run_*.py` directly**):

| Step | Skill | Writes to |
|------|-------|-----------|
| L0 | `analysis_skills/modem-l0-baseline/` | `analysis.l0_baseline` |
| L1 | `analysis_skills/modem-l1-business-judge/` | `analysis.l1_business` (`primary_domain`) |
| L2 | By domain: `ee` / `call` / `data` / `sim`; skip if `other` | `analysis.l2_domains.<domain>` |
| L3 | `analysis_skills/modem-l3-conclusion/` | `analysis.l3_conclusion`, `analysis.final_report` |

After each layer, **write back to manifest immediately** (see `references/manifest-update-guide.md`).

### 3.4 Log search helper

```powershell
$env:PYTHONIOENCODING = "utf-8"
python analysis_skills\log-search-read\scripts\log_search_read.py --manifest <MANIFEST_PATH> list
python analysis_skills\log-search-read\scripts\log_search_read.py --manifest <MANIFEST_PATH> search --query "SIM_STATE"
```

### 3.5 Delivery format

When analysis completes, the Agent outputs:

```text
[FINAL_REPORT_BEGIN]
<verbatim manifest.analysis.final_report>
[FINAL_REPORT_END]
```

Do not rewrite, summarize, or translate the `final_report` body.

### 3.6 Optional: update Feishu dashboard (**usually not used**)

Local analysis does **not** depend on the Feishu dashboard. Only when the user **explicitly asks** and `FEISHU_*` is configured:

```powershell
python scripts\finalize_analysis.py --manifest <MANIFEST_PATH> --skip-upload --skip-delete
```

### 3.7 Writing back to manifest

1. Preferred: precise JSON `str_replace`
2. Fallback: `python scripts/update_manifest.py --manifest <path> --stage l0 --data-file <json>`

Avoid: building JSON with `python -c`, rewriting the entire manifest file.

---

## 4. Directory layout

```text
modem-analysis-local/
├── SKILL.md              # Main Agent workflow
├── README.md
├── requirements.txt
├── .env.example          # Root config template
├── log-pipeline/         # Log preparation
├── analysis_skills/      # L0–L3
├── scripts/              # manifest / finalize
├── schemas/              # job_manifest.schema.json
└── references/           # setup, manifest guides, etc.
```

---

## 5. Troubleshooting

| Symptom | Suggestion |
|---------|------------|
| Jira / download failures | Verify `.env` and `log-pipeline\.env` are in sync; check `JIRA_SERVER` reachability |
| Extract / export failures | Set `SEVEN_ZIP_EXE`, `ELT_HOME`/`NLT_HOME`, or `QUTS_PYTHON_PATH` |
| Slow workspace | Move `WORKSPACE_ROOT` to local SSD; avoid UNC |
| `SKILL_FAILED:` on stdout | Report verbatim and stop (script-level failure) |
| Insufficient evidence | Record `gaps` and lower `confidence` per layer; not a SKILL_FAILED |

---

## 6. Related files

- Main workflow: `SKILL.md`
- Environment details: `references/setup.md`
- Manifest updates: `references/manifest-update-guide.md`
- Full pipeline env vars: `log-pipeline/.env.example`
- Chinese guide: [Feishu](https://transsioner.feishu.cn/docx/RwFgdfxt8oufDsxhg0Sc0g84nQg) · `references/feishu-setup-guide.md`
