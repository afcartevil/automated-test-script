"""Macro-redefinition include-order guidance for build_fix LLM."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.build_fix_service import _error_context_role
from web_app.llm_service import _macro_redefinition_guidance


def _err(file: str, line: int, kind: str, message: str, **extra):
    row = {"file": file, "line": line, "kind": kind, "message": message}
    row.update(extra)
    return row


_VENDOR = "vendor/mediatek/gpu/mali_malisw.h"
_GKI = "include/linux/minmax.h"


class MacroRedefContextRoleTests(unittest.TestCase):
    def test_gki_previous_definition_note_is_readonly(self):
        role = _error_context_role(_err(
            _GKI, 314, "note", "previous definition is here",
            note_kind="previous_definition",
        ))
        self.assertEqual(role, "readonly_macro_definition")

    def test_gki_error_is_readonly_even_when_primary(self):
        role = _error_context_role(_err(
            _GKI, 40, "error", "'MIN' macro redefined",
            error_priority="primary",
        ))
        self.assertEqual(role, "readonly_error_site")

    def test_vendor_previous_definition_is_fix_target(self):
        role = _error_context_role(_err(
            _VENDOR, 39, "note", "previous definition is here",
            note_kind="previous_definition",
        ))
        self.assertEqual(role, "previous_definition")

    def test_vendor_error_is_fix_target(self):
        role = _error_context_role(_err(
            _VENDOR, 39, "error", "'MIN' macro redefined",
            error_priority="primary",
        ))
        self.assertEqual(role, "primary_error")


class MacroRedefGuidanceTests(unittest.TestCase):
    def test_case1_deletes_vendor_define_at_error_site(self):
        text = _macro_redefinition_guidance([
            _err(_VENDOR, 39, "error", "'MIN' macro redefined [-Wmacro-redefined]"),
            _err(_GKI, 314, "note", "previous definition is here"),
        ])
        self.assertIn("情形 1", text)
        self.assertIn("在厂商 error 落点删除", text)
        self.assertIn(_VENDOR, text)
        self.assertIn("不要 `#ifndef`", text)

    def test_case2_deletes_vendor_define_not_gki(self):
        text = _macro_redefinition_guidance([
            _err(_GKI, 40, "error", "'MIN' macro redefined [-Wmacro-redefined]"),
            _err(_VENDOR, 39, "note", "previous definition is here"),
        ])
        self.assertIn("情形 2", text)
        self.assertIn("在厂商 note 处删除", text)
        self.assertIn(_VENDOR, text)
        self.assertNotIn("情形 1（本次命中）", text)


if __name__ == "__main__":
    unittest.main()
