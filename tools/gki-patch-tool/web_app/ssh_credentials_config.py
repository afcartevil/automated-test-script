"""SSH account storage in SQLite (settings UI → config table)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_LOCAL_SETTINGS_FILE = PROJECT_ROOT / "gki-patch-tool.local.yaml"

CREDENTIAL_KEYS = (
    "bastion_user",
    "bastion_password",
    "target_ip",
    "target_user",
    "target_password",
)

_MIGRATED_FROM_LOCAL = False


def _normalize_creds(raw: Dict[str, Any]) -> Dict[str, str]:
    out = {k: str(raw.get(k) or "").strip() for k in CREDENTIAL_KEYS}
    if not out.get("target_ip"):
        try:
            from web_app.ssh_bastion import load_bastion_config

            out["target_ip"] = load_bastion_config().target_ip
        except Exception:
            pass
    return out


def _credentials_from_legacy_yaml(settings: Dict[str, Any]) -> Dict[str, str]:
    creds = (settings.get("ssh_credentials") or {})
    if not creds:
        creds = (settings.get("ssh") or {}).get("credentials") or {}
    return _normalize_creds(creds if isinstance(creds, dict) else {})


def _migrate_legacy_local_yaml_once() -> None:
    """One-time: move gki-patch-tool.local.yaml into DB, then delete the file."""
    global _MIGRATED_FROM_LOCAL
    if _MIGRATED_FROM_LOCAL:
        return
    _MIGRATED_FROM_LOCAL = True

    from web_app.database import get_db_ssh_credentials, save_db_ssh_credentials

    if get_db_ssh_credentials().get("bastion_user"):
        if LEGACY_LOCAL_SETTINGS_FILE.is_file():
            try:
                LEGACY_LOCAL_SETTINGS_FILE.unlink()
            except OSError:
                pass
        return

    if not LEGACY_LOCAL_SETTINGS_FILE.is_file():
        return

    try:
        with LEGACY_LOCAL_SETTINGS_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            data = {}
    except OSError:
        return

    creds = _credentials_from_legacy_yaml(data)
    if creds.get("bastion_user"):
        save_db_ssh_credentials(creds)

    try:
        LEGACY_LOCAL_SETTINGS_FILE.unlink()
    except OSError:
        pass


def get_saved_ssh_credentials(*, require_passwords: bool = True) -> Optional[Dict[str, str]]:
    """Return SSH credentials saved via settings UI (SQLite config table)."""
    _migrate_legacy_local_yaml_once()
    from web_app.database import get_db_ssh_credentials

    creds = _normalize_creds(get_db_ssh_credentials())

    if require_passwords:
        for key in ("bastion_user", "bastion_password", "target_user", "target_password"):
            if not creds.get(key):
                return None
    elif not creds.get("bastion_user"):
        return None

    if not creds.get("target_ip"):
        return None
    return creds


def save_ssh_credentials(creds: Dict[str, Any]) -> None:
    from web_app.database import save_db_ssh_credentials

    save_db_ssh_credentials(_normalize_creds(creds))


def clear_ssh_credentials() -> None:
    """Remove saved SSH credentials from DB (does not touch in-memory job stash)."""
    from web_app.database import delete_db_ssh_credentials

    delete_db_ssh_credentials()
    if LEGACY_LOCAL_SETTINGS_FILE.is_file():
        try:
            LEGACY_LOCAL_SETTINGS_FILE.unlink()
        except OSError:
            pass


def get_ssh_credentials_api_payload() -> Dict[str, Any]:
    """For UI prefill / status."""
    creds = get_saved_ssh_credentials(require_passwords=False) or {}
    full = get_saved_ssh_credentials(require_passwords=True)
    return {
        "credentials_configured": full is not None,
        "bastion_user": creds.get("bastion_user", ""),
        "bastion_password": creds.get("bastion_password", ""),
        "target_ip": creds.get("target_ip", ""),
        "target_user": creds.get("target_user", ""),
        "target_password": creds.get("target_password", ""),
        "storage": "database",
    }
