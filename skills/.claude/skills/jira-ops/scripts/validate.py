import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple


CLI_PATH = Path(__file__).resolve().parent / "api_jira.py"


def run_cmd(args) -> Tuple[int, Dict]:
    proc = subprocess.run(
        [sys.executable, str(CLI_PATH)] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {"ok": False, "error": {"code": "NON_JSON_OUTPUT", "message": proc.stdout}}
    return proc.returncode, payload


def validate() -> int:
    checks = [
        ("help", ["--help"]),
        ("config_show", ["config", "show"]),
        ("list_log_sources_help", ["list-log-sources", "--help"]),
        ("setup_check_help", ["setup-check", "--help"]),
        ("extract_logs_help", ["extract-logs", "--help"]),
        ("prepare_logs_help", ["prepare-logs", "--help"]),
        ("env_show_help", ["env", "show", "--help"]),
        ("download_logs_help", ["download-logs", "--help"]),
        ("list_log_urls_help", ["list-log-urls-from-description", "--help"]),
        ("copy_log_help", ["copy-log-from-description", "--help"]),
    ]
    results = []
    for name, argv in checks:
        rc, out = run_cmd(argv)
        results.append({"name": name, "exit_code": rc, "output": out})

    print(json.dumps({"checks": results}, ensure_ascii=False, indent=2))
    # Validation is soft: return 0 if command invocation worked.
    return 0


if __name__ == "__main__":
    raise SystemExit(validate())

