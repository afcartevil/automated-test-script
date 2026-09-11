"""Interval patch lookup for direct upgrade (no prior analysis)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.interval_diff_service import (
    find_interval_patch_file,
    is_squash_patch_path,
    prefer_squash_sibling,
)


class IntervalPatchLookupTests(unittest.TestCase):
    def test_squash_path_detection(self):
        self.assertTrue(is_squash_patch_path(Path("a_to_b_squash.patch")))
        self.assertFalse(is_squash_patch_path(Path("a_to_b.patch")))

    def test_prefer_squash_sibling(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            fmt = tmp_path / "from_to.patch"
            squash = tmp_path / "from_to_squash.patch"
            fmt.write_text("format", encoding="utf-8")
            squash.write_text("squash", encoding="utf-8")
            self.assertEqual(prefer_squash_sibling(fmt), squash)
            self.assertEqual(prefer_squash_sibling(squash), squash)

    def test_find_interval_patch_uses_squash_on_disk(self):
        from_tag = "android13-5.15-2025-09_r9"
        to_tag = "android13-5.15-2026-03_r16"
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            fmt = tmp_path / f"{from_tag}_to_{to_tag}.patch"
            squash = tmp_path / f"{from_tag}_to_{to_tag}_squash.patch"
            fmt.write_text("format", encoding="utf-8")
            squash.write_text("squash", encoding="utf-8")
            with patch(
                "web_app.interval_diff_service.get_interval_diff",
                return_value=None,
            ), patch(
                "web_app.interval_diff_service.find_interval_diff_by_tags",
                return_value=None,
            ), patch(
                "web_app.interval_diff_service.interval_diff_paths",
                return_value=(fmt, squash),
            ):
                found = find_interval_patch_file(
                    "https://example/kernel", from_tag, to_tag,
                )
            self.assertEqual(found, squash)

    def test_find_interval_patch_accepts_squash_only(self):
        from_tag = "android13-5.15-2025-09_r9"
        to_tag = "android13-5.15-2026-03_r16"
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            fmt = tmp_path / f"{from_tag}_to_{to_tag}.patch"
            squash = tmp_path / f"{from_tag}_to_{to_tag}_squash.patch"
            squash.write_text("squash", encoding="utf-8")
            with patch(
                "web_app.interval_diff_service.get_interval_diff",
                return_value=None,
            ), patch(
                "web_app.interval_diff_service.find_interval_diff_by_tags",
                return_value=None,
            ), patch(
                "web_app.interval_diff_service.interval_diff_paths",
                return_value=(fmt, squash),
            ):
                found = find_interval_patch_file("", from_tag, to_tag)
            self.assertEqual(found, squash)

    def test_find_interval_patch_by_tags_ignores_repo_url(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            squash = tmp_path / "a_to_b_squash.patch"
            squash.write_text("squash", encoding="utf-8")
            row = {
                "diff_file": str(tmp_path / "missing.patch"),
                "squash_file": str(squash),
            }
            with patch(
                "web_app.interval_diff_service.get_interval_diff",
                return_value=None,
            ), patch(
                "web_app.interval_diff_service.find_interval_diff_by_tags",
                return_value=row,
            ), patch(
                "web_app.interval_diff_service.interval_diff_paths",
                return_value=(
                    tmp_path / "a_to_b.patch",
                    tmp_path / "a_to_b_squash.patch",
                ),
            ):
                found = find_interval_patch_file("https://other/repo", "a", "b")
            self.assertEqual(found, squash)


if __name__ == "__main__":
    unittest.main()
