"""Unaligned .rej hunks should still apply via context micro-patches."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.conflict_merge_service import (
    _try_unaligned_rej_micro_patches,
    resolve_conflict_file,
)
from web_app.conflict_region_utils import (
    _file_hunk_aligned,
    _micro_inserts_follow_context,
    _parse_hunk_sides,
    _parse_rej_hunks,
    _split_lines,
    assert_micro_inserts_follow_context,
    collect_conflict_merge_tasks,
    count_c_function_defs,
    extra_function_defs_introduced,
    function_impl_diverged_from_gki,
)


def _vendor() -> str:
    pad = "\n".join(f"static void pad_{i}(void) {{}}" for i in range(80))
    body = """
static int mtk_i2c_transfer(struct i2c_adapter *adap,
			    struct i2c_msg msgs[], int num)
{
	int ret;
	int left_num = num;
	struct mtk_i2c *i2c = i2c_get_adapdata(adap);

	/* vendor extra probe kept on purpose */
	if (i2c->dev_comp->quirk)
		left_num = num;

	if (!i2c->auto_restart) {
		if (num > 1) {
			i2c->op = I2C_MASTER_WRRD;
			left_num--;
		}
	}

	ret = mtk_i2c_do_transfer(i2c, msgs, num, left_num);
	if (ret < 0)
		goto err_exit;

	msgs++;
	return ret;
err_exit:
	return ret;
}
"""
    return pad + body + "\n"


_REJ = """diff a/drivers/i2c/busses/i2c-mt65xx.c b/drivers/i2c/busses/i2c-mt65xx.c	(rejected hunks)
@@ -1065,20 +1065,21 @@ static int mtk_i2c_do_transfer(struct mtk_i2c *i2c, struct i2c_msg *msgs,
 static int mtk_i2c_transfer(struct i2c_adapter *adap,
 			    struct i2c_msg msgs[], int num)
 {
 	int ret;
 	int left_num = num;
+	bool write_then_read_en = false;
 	struct mtk_i2c *i2c = i2c_get_adapdata(adap);
 
-	if (!i2c->auto_restart) {
-		if (num > 1) {
-			i2c->op = I2C_MASTER_WRRD;
-			left_num--;
-		}
+	if (write_then_read_en) {
+		i2c->op = I2C_MASTER_WRRD;
+		left_num--;
 	}
 
 	ret = mtk_i2c_do_transfer(i2c, msgs, num, left_num);
 	if (ret < 0)
 		goto err_exit;
 
-	msgs++;
+	if (i2c->op == I2C_MASTER_WRRD)
+		msgs += 2;
+	else
+		msgs++;
 	return ret;
"""


class UnalignedRejMicroPatchTests(unittest.TestCase):
    def test_micro_patch_applies_when_hunk_window_missing(self):
        vendor = _vendor()
        result = _try_unaligned_rej_micro_patches(
            vendor, _REJ, job_id="t", source_path="drivers/i2c/busses/i2c-mt65xx.c",
        )
        self.assertIsNotNone(result)
        proposed, summary, strategy = result
        self.assertEqual(strategy, "deterministic")
        self.assertIn("rej微补丁", summary)
        self.assertIn("bool write_then_read_en = false;", proposed)
        self.assertIn("msgs += 2;", proposed)
        self.assertIn("vendor extra probe kept on purpose", proposed)
        self.assertEqual(count_c_function_defs(proposed, "mtk_i2c_transfer"), 1)

    def test_resolve_falls_back_when_no_aligned_tasks(self):
        vendor = _vendor()
        with patch(
            "web_app.conflict_merge_service.load_gki_file_versions",
            return_value=(None, None),
        ), patch(
            "web_app.conflict_merge_service.collect_conflict_merge_tasks",
            return_value=[],
        ):
            proposed, summary, strategy = resolve_conflict_file(
                {"from_tag": "a", "to_tag": "b"},
                job_id="t",
                source_path="drivers/i2c/busses/i2c-mt65xx.c",
                original_content=vendor,
                rej_content=_REJ,
            )
        self.assertEqual(strategy, "deterministic")
        self.assertIn("rej微补丁", summary)
        self.assertIn("msgs += 2;", proposed)
        self.assertIn("vendor extra probe kept on purpose", proposed)
        self.assertEqual(count_c_function_defs(proposed, "mtk_i2c_transfer"), 1)

    def test_resolve_still_errors_when_micro_patch_cannot_apply(self):
        with patch(
            "web_app.conflict_merge_service.load_gki_file_versions",
            return_value=(None, None),
        ), patch(
            "web_app.conflict_merge_service.collect_conflict_merge_tasks",
            return_value=[],
        ):
            with self.assertRaisesRegex(RuntimeError, "无法在当前源文件中定位"):
                resolve_conflict_file(
                    {"from_tag": "a", "to_tag": "b"},
                    job_id="t",
                    source_path="drivers/i2c/busses/i2c-mt65xx.c",
                    original_content="static void unrelated(void) {}\n",
                    rej_content=_REJ,
                )


class DivergedFunctionIncrementalTests(unittest.TestCase):
    def test_detects_same_name_different_body(self):
        orig = _split_lines(_vendor())
        _os, _oc, _ns, _nc, body = _parse_rej_hunks(_REJ)[0]
        hunk_old, _ = _parse_hunk_sides(body)
        self.assertTrue(function_impl_diverged_from_gki(orig, hunk_old, body))
        self.assertEqual(count_c_function_defs(_vendor(), "mtk_i2c_transfer"), 1)

    def test_first_line_only_is_not_aligned(self):
        hunk_old = [
            "static int mtk_i2c_transfer(struct i2c_adapter *adap,",
            "			    struct i2c_msg msgs[], int num)",
            "{",
            "	int ret;",
        ]
        src = [
            "static int mtk_i2c_transfer(struct i2c_adapter *adap,",
            "			    struct i2c_msg msgs[], int num);",
            "static void other(void) {}",
            "int x;",
        ]
        self.assertFalse(_file_hunk_aligned(src, 0, hunk_old))

    def test_does_not_paste_gki_function_at_rej_lineno(self):
        """Old first-line align would paste GKI mtk_i2c_transfer at line 1065."""
        pads = [f"static void pad_{i}(void) {{}}" for i in range(1064)]
        decoy = [
            "static int mtk_i2c_transfer(struct i2c_adapter *adap,",
            "			    struct i2c_msg msgs[], int num);",
            "static void decoy_tail(void) {}",
        ]
        func_only = _vendor().split("static int mtk_i2c_transfer", 1)[1]
        source = "\n".join(pads + decoy) + "\nstatic int mtk_i2c_transfer" + func_only
        self.assertEqual(count_c_function_defs(source, "mtk_i2c_transfer"), 1)
        self.assertEqual(collect_conflict_merge_tasks(
            original_content=source, rej_content=_REJ,
        ), [])

        with patch(
            "web_app.conflict_merge_service.load_gki_file_versions",
            return_value=(None, None),
        ):
            proposed, _summary, strategy = resolve_conflict_file(
                {"from_tag": "a", "to_tag": "b"},
                job_id="t",
                source_path="drivers/i2c/busses/i2c-mt65xx.c",
                original_content=source,
                rej_content=_REJ,
            )
        self.assertEqual(strategy, "deterministic")
        self.assertEqual(count_c_function_defs(proposed, "mtk_i2c_transfer"), 1)
        self.assertEqual(extra_function_defs_introduced(source, proposed, _REJ), [])
        self.assertIn("vendor extra probe kept on purpose", proposed)
        self.assertIn("bool write_then_read_en = false;", proposed)
        self.assertIn("msgs += 2;", proposed)
        # prototype at the .rej line must stay a prototype, not a second function
        self.assertIn(
            "static int mtk_i2c_transfer(struct i2c_adapter *adap,\n"
            "			    struct i2c_msg msgs[], int num);",
            proposed,
        )

    def test_kind_a_does_not_replace_diverged_vendor_function(self):
        vendor = _vendor()
        func_start = vendor.index("static int mtk_i2c_transfer")
        start_line = vendor[:func_start].count("\n")
        func_text = vendor[func_start:]
        _os, _oc, _ns, _nc, hunk_body = _parse_rej_hunks(_REJ)[0]
        _old, hunk_new = _parse_hunk_sides(hunk_body)
        end_line = start_line + func_text.count("\n")
        task = {
            "index": 1,
            "total": 1,
            "start_line": start_line + 1,
            "end_line": end_line,
            "replace_start": start_line,
            "replace_end": end_line,
            "pre_len": 0,
            "post_len": 0,
            "aligned": True,
            "vendor_snippet": func_text.strip("\n"),
            "body_snippet": func_text.strip("\n"),
            "incoming_snippet": "\n".join(hunk_new),
            "incoming_body_snippet": "\n".join(hunk_new),
            "hunk_body": hunk_body,
            "kind": "rej",
        }
        with patch(
            "web_app.conflict_merge_service.load_gki_file_versions",
            return_value=(None, None),
        ), patch(
            "web_app.conflict_merge_service._try_unaligned_rej_micro_patches",
            return_value=None,
        ), patch(
            "web_app.conflict_merge_service.collect_conflict_merge_tasks",
            return_value=[task],
        ), patch(
            "web_app.conflict_merge_service.classify_hunk",
            return_value="A",
        ):
            proposed, _summary, _strategy = resolve_conflict_file(
                {"from_tag": "a", "to_tag": "b"},
                job_id="t",
                source_path="drivers/i2c/busses/i2c-mt65xx.c",
                original_content=vendor,
                rej_content=_REJ,
            )
        self.assertEqual(count_c_function_defs(proposed, "mtk_i2c_transfer"), 1)
        self.assertIn("vendor extra probe kept on purpose", proposed)
        self.assertIn("bool write_then_read_en = false;", proposed)
        self.assertIn("msgs += 2;", proposed)


class VendorContinuousWrAnchorTests(unittest.TestCase):
    def test_true_flag_stays_in_wrrd_check_not_after_for_loop(self):
        data = ROOT / "tests" / "testdata"
        vendor_fn = (data / "i2c-mt65xx.vendor_fn.c").read_text(encoding="utf-8")
        rej = (data / "i2c-mt65xx.c.rej").read_text(encoding="utf-8")
        pad = "\n".join(f"static void pad_{i}(void) {{}}" for i in range(80))
        vendor = pad + "\n" + vendor_fn
        result = _try_unaligned_rej_micro_patches(
            vendor, rej,
            job_id="t", source_path="drivers/i2c/busses/i2c-mt65xx.c",
        )
        self.assertIsNotNone(result)
        proposed, _summary, strategy = result
        self.assertEqual(strategy, "deterministic")
        self.assertIn("I2C_MASTER_CONTINUOUS_WR", proposed)
        self.assertRegex(
            proposed,
            r"i2c->auto_restart = 0;\s*\n\s*write_then_read_en = true;",
        )
        self.assertNotRegex(
            proposed,
            r"else\s*\n\s*break;\s*\n\s*\}\s*\n\s*write_then_read_en = true;",
        )

    def test_misplaced_true_flag_is_rejected(self):
        data = ROOT / "tests" / "testdata"
        vendor_fn = (data / "i2c-mt65xx.vendor_fn.c").read_text(encoding="utf-8")
        rej = (data / "i2c-mt65xx.c.rej").read_text(encoding="utf-8")
        wrong = vendor_fn.replace(
            "			} else\n				break;\n		}",
            "			} else\n				break;\n		}\n			write_then_read_en = true;",
            1,
        )
        wrong = wrong.replace(
            "	int left_num = num;\n",
            "	int left_num = num;\n	bool write_then_read_en = false;\n",
            1,
        )
        self.assertIn("write_then_read_en = true;", wrong)
        self.assertFalse(_micro_inserts_follow_context(wrong, rej))
        hunk_body = _parse_rej_hunks(rej)[0][4]
        self.assertFalse(_micro_inserts_follow_context(wrong, hunk_body))

    def test_llm_path_rejects_misplaced_insert(self):
        data = ROOT / "tests" / "testdata"
        vendor_fn = (data / "i2c-mt65xx.vendor_fn.c").read_text(encoding="utf-8")
        rej = (data / "i2c-mt65xx.c.rej").read_text(encoding="utf-8")
        pad = "\n".join(f"static void pad_{i}(void) {{}}" for i in range(80))
        vendor = pad + "\n" + vendor_fn
        result = _try_unaligned_rej_micro_patches(
            vendor, rej,
            job_id="t", source_path="drivers/i2c/busses/i2c-mt65xx.c",
        )
        self.assertIsNotNone(result)
        proposed = result[0]
        misplaced = re.sub(
            r"(i2c->auto_restart = 0;\n)\t+write_then_read_en = true;\n",
            r"\1",
            proposed,
            count=1,
        )
        self.assertNotEqual(misplaced, proposed)
        misplaced = misplaced.replace(
            "			} else\n				break;\n		}",
            "			} else\n				break;\n		}\n			write_then_read_en = true;",
            1,
        )
        with self.assertRaisesRegex(RuntimeError, "紧挨其 context"):
            assert_micro_inserts_follow_context(misplaced, rej)
        hunk_body = _parse_rej_hunks(rej)[0][4]
        task = {
            "index": 1,
            "total": 1,
            "start_line": 1,
            "end_line": 10,
            "replace_start": 80,
            "replace_end": 200,
            "pre_len": 0,
            "post_len": 0,
            "vendor_snippet": vendor_fn,
            "body_snippet": vendor_fn,
            "hunk_body": hunk_body,
            "incremental_only": True,
            "kind": "rej",
        }
        with patch(
            "web_app.conflict_merge_service.load_gki_file_versions",
            return_value=(None, None),
        ), patch(
            "web_app.conflict_merge_service._try_unaligned_rej_micro_patches",
            return_value=None,
        ), patch(
            "web_app.conflict_merge_service.collect_conflict_merge_tasks",
            return_value=[task],
        ), patch(
            "web_app.conflict_merge_service.classify_hunk",
            return_value="C",
        ), patch(
            "web_app.conflict_merge_service.apply_rej_hunk_micro_patches",
            return_value=(vendor, 0),
        ), patch(
            "web_app.llm_service.is_llm_configured",
            return_value=True,
        ), patch(
            "web_app.llm_service.resolve_merge_conflict_tasks_via_llm",
            return_value=(misplaced, "llm misplaced"),
        ):
            with self.assertRaisesRegex(RuntimeError, "紧挨其 context"):
                resolve_conflict_file(
                    {"from_tag": "a", "to_tag": "b"},
                    job_id="t",
                    source_path="drivers/i2c/busses/i2c-mt65xx.c",
                    original_content=vendor,
                    rej_content=rej,
                )


if __name__ == "__main__":
    unittest.main()

