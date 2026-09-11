"""Implementation logic is a hint to prefer the right branch, not the only rule."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.conflict_region_utils import (
    apply_rej_hunk_micro_patches,
    build_function_logic_hints,
)


_VENDOR = """
static int foo(int mode)
{
	int x = 0;
	/* wrrd path */
	if (mode == WRRD) {
		x = 0;
	}
	if (mode == CONTINUOUS) {
		x = 0;
		do_continuous();
	}
	return x;
}
"""

_REJ = """
 static int foo(int mode)
 {
 	int x = 0;
 	/* wrrd path */
 	if (mode == WRRD) {
 		x = 0;
+		flag = true;
 	}
 	return x;
 }
"""


class LogicHintAssistTests(unittest.TestCase):
    def test_prefers_matching_branch_when_same_stmt_appears_twice(self):
        merged, n = apply_rej_hunk_micro_patches(_VENDOR, _REJ)
        self.assertGreater(n, 0)
        self.assertRegex(
            merged,
            r"if \(mode == WRRD\) \{\s*\n\s*x = 0;\s*\n\s*flag = true;",
        )
        self.assertNotRegex(
            merged,
            r"if \(mode == CONTINUOUS\) \{\s*\n\s*x = 0;\s*\n\s*flag = true;",
        )

    def test_falls_back_when_if_condition_text_differs(self):
        vendor = _VENDOR.replace("if (mode == WRRD)", "if (mode == WRITE_THEN_READ)")
        merged, n = apply_rej_hunk_micro_patches(vendor, _REJ)
        self.assertGreater(n, 0)
        self.assertIn("flag = true;", merged)
        self.assertRegex(
            merged,
            r"x = 0;\s*\n\s*flag = true;\s*\n\s*\}",
        )

    def test_hints_are_reference_not_sole_rule(self):
        hint = build_function_logic_hints(_REJ, _VENDOR)
        self.assertIn("辅助合入", hint)
        self.assertIn("不是唯一规则", hint)
        self.assertIn("WRRD", hint)
        self.assertIn("CONTINUOUS", hint)


if __name__ == "__main__":
    unittest.main()
