"""Machine-local GKI settings (survives switching easyadapter checkouts).

Settings UI still writes SQLite for the running instance; this JSON is the
cross-checkout copy under ~/.tahp-console (or TAHP_CONSOLE_HOME).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

_FILE_NAME = "gki-patch-settings.json"


def machine_settings_path() -> Path:
    override = os.environ.get("GKI_USER_SETTINGS", "").strip()
    if override:
        return Path(override).expanduser()
    home = os.environ.get("TAHP_CONSOLE_HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home() / ".tahp-console"
    return base / _FILE_NAME


def load_machine_settings() -> Dict[str, Any]:
    path = machine_settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_machine_settings(data: Dict[str, Any]) -> Path:
    path = machine_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_machine_settings()
    merged = {**current, **(data or {})}
    payload = json.dumps(merged, ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def settings_has_values(data: Dict[str, Any]) -> bool:
    if not data:
        return False
    if str(data.get("repo_dir") or "").strip():
        return True
    if str(data.get("apply_mode") or "").strip():
        return True
    llm = data.get("llm") if isinstance(data.get("llm"), dict) else {}
    if any(str(llm.get(k) or "").strip() for k in ("api_key", "api_base", "model")):
        return True
    feishu = data.get("feishu") if isinstance(data.get("feishu"), dict) else {}
    if any(str(v or "").strip() for v in feishu.values()):
        return True
    ssh = data.get("ssh_credentials") if isinstance(data.get("ssh_credentials"), dict) else {}
    if any(str(v or "").strip() for v in ssh.values()):
        return True
    hints = data.get("retry_hints") if isinstance(data.get("retry_hints"), dict) else {}
    if any(str(v or "").strip() for v in hints.values()):
        return True
    return False


RETRY_HINT_DOMAINS = ("conflict", "build_fix")
_RETRY_HINT_MAX_CHARS = 8000


def get_retry_hints(domain: str) -> str:
    data = load_machine_settings()
    hints = data.get("retry_hints") if isinstance(data.get("retry_hints"), dict) else {}
    return str(hints.get(domain) or "").strip()


def set_retry_hints(domain: str, text: str) -> str:
    if domain not in RETRY_HINT_DOMAINS:
        raise ValueError(f"未知 hint 域: {domain}")
    data = load_machine_settings()
    hints = dict(data.get("retry_hints") if isinstance(data.get("retry_hints"), dict) else {})
    cleaned = (text or "").strip()
    if cleaned:
        hints[domain] = cleaned[:_RETRY_HINT_MAX_CHARS]
    else:
        hints.pop(domain, None)
    data["retry_hints"] = hints
    save_machine_settings(data)
    return str(hints.get(domain) or "").strip()


def append_retry_hint(domain: str, text: str) -> str:
    """Append a user retry note into the persistent prompt hint for this domain."""
    note = (text or "").strip()
    if not note:
        return get_retry_hints(domain)
    existing = get_retry_hints(domain)
    if note in existing:
        return existing
    combined = f"{existing}\n\n{note}".strip() if existing else note
    if len(combined) > _RETRY_HINT_MAX_CHARS:
        combined = combined[-_RETRY_HINT_MAX_CHARS:]
    return set_retry_hints(domain, combined)
