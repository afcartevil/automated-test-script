"""Machine-local GKI settings JSON."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.user_settings import (
    load_machine_settings,
    machine_settings_path,
    save_machine_settings,
    settings_has_values,
)


class MachineSettingsTests(unittest.TestCase):
    def test_path_honors_env_override(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "settings.json"
            old = os.environ.get("GKI_USER_SETTINGS")
            os.environ["GKI_USER_SETTINGS"] = str(target)
            try:
                self.assertEqual(machine_settings_path(), target)
            finally:
                if old is None:
                    os.environ.pop("GKI_USER_SETTINGS", None)
                else:
                    os.environ["GKI_USER_SETTINGS"] = old

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "gki-patch-settings.json"
            old = os.environ.get("GKI_USER_SETTINGS")
            os.environ["GKI_USER_SETTINGS"] = str(target)
            try:
                payload = {
                    "repo_dir": r"E:\code\kernel\common",
                    "feishu": {"app_id": "cli_xxx", "owner": "ke.li11@transsion.com"},
                }
                save_machine_settings(payload)
                loaded = load_machine_settings()
                self.assertEqual(loaded["repo_dir"], payload["repo_dir"])
                self.assertEqual(loaded["feishu"]["app_id"], "cli_xxx")
                self.assertTrue(target.is_file())
            finally:
                if old is None:
                    os.environ.pop("GKI_USER_SETTINGS", None)
                else:
                    os.environ["GKI_USER_SETTINGS"] = old

    def test_has_values(self):
        self.assertFalse(settings_has_values({}))
        self.assertFalse(settings_has_values({"repo_dir": "  ", "llm": {}}))
        self.assertTrue(settings_has_values({"repo_dir": "E:\\k"}))
        self.assertTrue(settings_has_values({"feishu": {"app_id": "cli"}}))

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "missing.json"
            old = os.environ.get("GKI_USER_SETTINGS")
            os.environ["GKI_USER_SETTINGS"] = str(target)
            try:
                self.assertEqual(load_machine_settings(), {})
            finally:
                if old is None:
                    os.environ.pop("GKI_USER_SETTINGS", None)
                else:
                    os.environ["GKI_USER_SETTINGS"] = old


if __name__ == "__main__":
    unittest.main()
