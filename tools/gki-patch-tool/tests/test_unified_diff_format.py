"""make_unified_diff must emit --- / +++ / @@ on separate lines."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.conflict_resolution_service import make_unified_diff


class MakeUnifiedDiffTests(unittest.TestCase):
    def test_hunk_header_is_on_its_own_line(self):
        before = "aaa\n#define MIN(a, b) ((a) < (b) ? (a) : (b))\nccc\n"
        after = "aaa\nccc\n"
        diff = make_unified_diff("drivers/char/rpmb/rpmb-mtk.c", before, after)
        self.assertNotIn("+++", diff.split("\n")[0])
        self.assertRegex(diff, r"(?m)^@@ -\d+")
        m = re.search(r"^@@ -(\d+),", diff, re.M)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 1)


if __name__ == "__main__":
    unittest.main()
