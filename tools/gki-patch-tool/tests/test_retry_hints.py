"""Persistent retry hints and prompt suffix for conflict / build-fix."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.prompt_loader import (
    get_session_retry_hint,
    set_session_retry_hint,
    user_hint_prompt_suffix,
)
from web_app.user_settings import (
    append_retry_hint,
    get_retry_hints,
    save_machine_settings,
    set_retry_hints,
)


class RetryHintTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = Path(self._tmp.name) / "gki-patch-settings.json"
        self._old = os.environ.get("GKI_USER_SETTINGS")
        os.environ["GKI_USER_SETTINGS"] = str(self._path)

    def tearDown(self):
        set_session_retry_hint("")
        if self._old is None:
            os.environ.pop("GKI_USER_SETTINGS", None)
        else:
            os.environ["GKI_USER_SETTINGS"] = self._old
        self._tmp.cleanup()

    def test_append_and_dedupe(self):
        append_retry_hint("conflict", "只合 +/-")
        append_retry_hint("conflict", "只合 +/-")
        self.assertEqual(get_retry_hints("conflict"), "只合 +/-")
        append_retry_hint("conflict", "保留 vendor 函数")
        text = get_retry_hints("conflict")
        self.assertIn("只合 +/-", text)
        self.assertIn("保留 vendor 函数", text)

    def test_merge_keeps_hints_when_other_settings_saved(self):
        append_retry_hint("build_fix", "不要改内核头")
        save_machine_settings({"repo_dir": r"E:\kernel"})
        self.assertEqual(get_retry_hints("build_fix"), "不要改内核头")
        self.assertEqual(save_machine_settings({"repo_dir": r"E:\kernel"}), self._path)

    def test_prompt_suffix_combines_saved_and_session(self):
        set_retry_hints("conflict", "经验A")
        set_session_retry_hint("本次B")
        block = user_hint_prompt_suffix("conflict")
        self.assertIn("经验A", block)
        self.assertIn("本次B", block)
        self.assertEqual(get_session_retry_hint(), "本次B")

    def test_llm_conflict_prompt_includes_hint(self):
        set_retry_hints("conflict", "禁止贴整函数")
        set_session_retry_hint("只改 msgs += 2")
        from web_app.llm_service import _resolve_conflict_region_via_llm

        captured = {}

        def fake_call(system, user, config, **kwargs):
            captured["system"] = system
            return "summary: ok\n```merged\nint x;\n```\n", {}

        task = {
            "index": 1,
            "total": 1,
            "start_line": 1,
            "end_line": 2,
            "kind": "rej",
            "body_snippet": "int x;",
            "vendor_snippet": "int x;",
            "pre_len": 0,
            "post_len": 0,
        }
        with patch("web_app.llm_service._call_llm", side_effect=fake_call), patch(
            "web_app.llm_service._validate_region_merge",
        ):
            _resolve_conflict_region_via_llm(
                source_path="drivers/i2c/busses/i2c-mt65xx.c",
                task=task,
                config={"api_key": "k", "api_base": "http://x", "model": "m"},
            )
        self.assertIn("禁止贴整函数", captured["system"])
        self.assertIn("只改 msgs += 2", captured["system"])


if __name__ == "__main__":
    unittest.main()
