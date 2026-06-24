# Standalone Setup

Use this shared setup when you copy the modem skills into another workspace.

## 1. Install Python packages

Install everything needed by the Python-backed skills:

```powershell
python -m pip install -r skills\_shared\requirements-all.txt
python -m playwright install chromium
```

Or install only the packages needed by selected skills:

```powershell
python -m pip install -r skills\jira-issue-fetch\requirements.txt
python -m pip install -r skills\box-log-download\requirements.txt
```

Each skill folder now includes its own `requirements.txt`.

You can also install selected skills with the helper script:

```powershell
python skills\_shared\install_python_deps.py --skill jira-issue-fetch --skill box-log-download
```

`install_python_deps.py` 会在包含 `playwright` 依赖时自动执行 `playwright install chromium`。

## 2. Check external runtimes

```powershell
python skills\_shared\check_environment.py
```

This reports:

- Python packages for Jira and Playwright-backed skills
- Chrome / Edge availability for `box-log-download`
- 7-Zip availability for `.rar` / `.7z` extraction
- `ELT_HOME` / `NLT_HOME` availability for `elt-nlt-export`
- Python 3.7 availability for the ELT path
- Python 3.12 availability for the NLT path

## 3. Configure credentials and paths

Common environment variables:

```powershell
$env:JIRA_SERVER="http://jira.transsion.com"
$env:JIRA_USERNAME="<your-jira-username>"
$env:JIRA_PASSWORD="<your-jira-password-or-token>"
$env:ELT_HOME="C:\ELT"
$env:NLT_HOME="C:\NLT"
$env:SEVEN_ZIP_EXE="C:\Program Files\7-Zip\7z.exe"
```

## 4. Start with a manifest

Copy and edit:

- `skills/_shared/job_manifest.example.json`

Then run the atomic skills in sequence or use the orchestrator skill.
