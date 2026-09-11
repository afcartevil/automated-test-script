"""Parse and truncation detection for build_fix LLM replies."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.llm_service import _llm_output_truncated, _parse_build_fix_blocks


_CLOSED = """summary: 删除 vendor MIN 宏，修复宏重定义

```fix drivers/char/rpmb/rpmb-mtk.c
--- a/drivers/char/rpmb/rpmb-mtk.c
+++ b/drivers/char/rpmb/rpmb-mtk.c
@@ -130,7 +130,6 @@
  */
-#define MIN(a, b) (((a) < (b)) ? (a) : (b))

 int rpmb_init(void)
```
"""

_TRUNCATED = """summary: 删除 vendor MIN 宏

```fix drivers/char/rpmb/rpmb-mtk.c
--- a/drivers/char/rpmb/rpmb-mtk.c
+++ b/drivers/char/rpmb/rpmb-mtk.c
@@ -130,7 +130,6 @@
-#define MIN(a, b) (((a) < (b)) ? (a) : (b))
"""


class BuildFixLlmParseTests(unittest.TestCase):
    def test_parse_closed_fix_block(self):
        fixes, summary = _parse_build_fix_blocks(_CLOSED)
        self.assertIn("MIN", summary)
        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0]["path"], "drivers/char/rpmb/rpmb-mtk.c")
        self.assertIn("-#define MIN", fixes[0]["content"])

    def test_truncated_unclosed_fence_is_not_a_valid_fix(self):
        fixes, _ = _parse_build_fix_blocks(_TRUNCATED)
        self.assertEqual(fixes, [])
        self.assertTrue(_llm_output_truncated(_TRUNCATED, {}, 2048))

    def test_truncated_when_completion_hits_max_tokens(self):
        self.assertTrue(
            _llm_output_truncated("summary: x", {"completion_tokens": 2048}, 2048)
        )
        self.assertTrue(
            _llm_output_truncated("summary: x", {"finish_reason": "length"}, 8192)
        )
        self.assertFalse(
            _llm_output_truncated(_CLOSED, {"completion_tokens": 400, "finish_reason": "stop"}, 8192)
        )


if __name__ == "__main__":
    unittest.main()
