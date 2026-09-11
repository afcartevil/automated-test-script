"""Function-level 3-way merge uses GKI old/new implementations."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.conflict_merge_service import (
    _attach_function_impl_hints,
    _try_function_level_three_way,
    resolve_conflict_file,
)
from web_app.conflict_region_utils import extract_named_c_function

_BASE_FOO = """
static int foo(int x)
{
	int ret = x;
	if (ret) {
		ret = 0;
	}
	return ret;
}
"""

_THEIRS_FOO = """
static int foo(int x)
{
	int ret = x;
	bool flag = false;
	if (ret) {
		ret = 0;
		flag = true;
	}
	if (flag)
		return 2;
	return ret;
}
"""

_OURS_FOO = """
static int foo(int x)
{
	int ret = x;
	if (ret) {
		ret = 0;
	}
	/* vendor extra */
	if (ret > 1) {
		ret = 9;
	}
	return ret;
}
"""

_BAR_BASE = """
static int bar(void)
{
	return 1;
}
"""

_BAR_THEIRS = """
static int bar(void)
{
	return 2;
}
"""

_BAR_OURS = """
static int bar(void)
{
	return 3;
}
"""

_REJ_FOO = """diff a/foo.c b/foo.c	(rejected hunks)
@@ -1,8 +1,11 @@ static int foo(int x)
 static int foo(int x)
 {
 	int ret = x;
+	bool flag = false;
 	if (ret) {
 		ret = 0;
+		flag = true;
 	}
+	if (flag)
+		return 2;
 	return ret;
 }
"""


def _file(*parts: str) -> str:
    return "\n".join(p.strip("\n") for p in parts) + "\n"


class ExtractNamedCFunctionTests(unittest.TestCase):
    def test_skips_prototype(self):
        src = (
            "static int foo(int x);\n"
            "static int foo(int x)\n"
            "{\n"
            "	return x;\n"
            "}\n"
        )
        located = extract_named_c_function(src, "foo")
        self.assertIsNotNone(located)
        start, _end, text = located
        self.assertIn("return x;", text)
        self.assertGreater(start, 0)
        self.assertTrue(text.lstrip().startswith("static int foo(int x)"))


class FunctionLevelThreeWayTests(unittest.TestCase):
    def test_keeps_vendor_block_and_applies_gki_insert(self):
        ours = _file(_OURS_FOO)
        base = _file(_BASE_FOO)
        theirs = _file(_THEIRS_FOO)
        result = _try_function_level_three_way(
            ours, _REJ_FOO, base, theirs,
            job_id="t", source_path="foo.c",
        )
        self.assertIsNotNone(result)
        merged, summary, strategy = result
        self.assertEqual(strategy, "function_merge")
        self.assertIn("函数级三路合并", summary)
        self.assertIn("/* vendor extra */", merged)
        self.assertIn("ret = 9;", merged)
        self.assertIn("bool flag = false;", merged)
        self.assertRegex(
            merged,
            r"ret = 0;\s*\n\s*flag = true;",
        )
        self.assertIn("if (flag)", merged)

    def test_resolve_uses_function_merge_when_whole_file_conflicts(self):
        ours = _file(_OURS_FOO, _BAR_OURS)
        base = _file(_BASE_FOO, _BAR_BASE)
        theirs = _file(_THEIRS_FOO, _BAR_THEIRS)
        with patch(
            "web_app.conflict_merge_service.load_gki_file_versions",
            return_value=(base, theirs),
        ), patch(
            "web_app.conflict_merge_service._try_unaligned_rej_micro_patches",
            return_value=None,
        ):
            proposed, summary, strategy = resolve_conflict_file(
                {"from_tag": "a", "to_tag": "b"},
                job_id="t",
                source_path="foo.c",
                original_content=ours,
                rej_content=_REJ_FOO,
            )
        self.assertEqual(strategy, "function_merge")
        self.assertIn("vendor extra", proposed)
        self.assertIn("flag = true;", proposed)
        self.assertIn("return 3;", proposed)
        self.assertIn("函数级三路合并", summary)

    def test_attach_hints_includes_old_new_and_conflict_preview(self):
        task = {
            "hunk_body": _parse_hunk_for_test(),
        }
        ours = _file(_OURS_FOO, _BAR_OURS)
        base = _file(_BASE_FOO, _BAR_BASE)
        theirs = _file(_THEIRS_FOO, _BAR_THEIRS)
        _attach_function_impl_hints(task, ours, base, theirs)
        self.assertIn("ret = 0;", task.get("gki_old_function") or "")
        self.assertIn("flag = true;", task.get("gki_new_function") or "")
        self.assertIn("vendor extra", task.get("vendor_function") or "")


def _parse_hunk_for_test() -> str:
    from web_app.conflict_region_utils import _parse_rej_hunks
    return _parse_rej_hunks(_REJ_FOO)[0][4]


if __name__ == "__main__":
    unittest.main()
