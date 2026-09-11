"""Conflict UI regions must be vendor-repo before/after, not GKI .rej sides."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.conflict_region_utils import extract_conflict_regions

_REJ = """diff a/foo.c b/foo.c	(rejected hunks)
@@ -1,8 +1,9 @@ static int foo(void)
 static int foo(void)
 {
 	int x = 0;
 	if (x) {
 		x = 0;
+		flag = true;
 	}
 	return x;
 }
"""

_VENDOR = """
static int foo(void)
{
	int x = 0;
	if (x) {
		x = 0;
	}
	/* vendor extra */
	if (x > 1) {
		x = 9;
	}
	return x;
}
"""

_PROPOSED = """
static int foo(void)
{
	int x = 0;
	if (x) {
		x = 0;
		flag = true;
	}
	/* vendor extra */
	if (x > 1) {
		x = 9;
	}
	return x;
}
"""


class VendorRepoCompareTests(unittest.TestCase):
    def test_proposed_diff_keeps_vendor_extra_not_gki_hunk(self):
        regions = extract_conflict_regions(
            kind="rej",
            original=_VENDOR,
            rej_content=_REJ,
            proposed=_PROPOSED,
        )
        self.assertTrue(regions)
        left = "\n".join(r.get("vendor") or "" for r in regions)
        right = "\n".join(r.get("merged") or "" for r in regions)
        self.assertIn("vendor extra", left)
        self.assertIn("vendor extra", right)
        self.assertIn("flag = true;", right)
        self.assertNotIn("flag = true;", left)

    def test_pending_shows_vendor_function_not_gki_old(self):
        regions = extract_conflict_regions(
            kind="rej",
            original=_VENDOR,
            rej_content=_REJ,
            proposed="",
        )
        self.assertTrue(regions)
        left = "\n".join(r.get("vendor") or "" for r in regions)
        self.assertIn("vendor extra", left)
        self.assertFalse(any((r.get("merged") or "").strip() for r in regions))


if __name__ == "__main__":
    unittest.main()
