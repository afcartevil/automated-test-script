"""Crash analysis entry modes and uncapped tag..HEAD fix search."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.crash_fix_search import (
    collect_fix_candidates,
    list_commits_after_tag,
    select_community_branches,
)
from web_app.crash_analysis_service import start_crash_analysis, _build_crash_report


class CrashFixSearchTests(unittest.TestCase):
    def test_list_commits_after_tag_has_no_max_count(self):
        captured = {}

        def fake_run_git(_repo, args, timeout=None):
            captured["args"] = list(args)
            return "abc123\x01fix panic in foo\n"

        with patch("tools.patch_analyzer.run_git", fake_run_git):
            rows = list_commits_after_tag("/repo", "android13-5.15-2026-03_r16")

        self.assertEqual(captured["args"][0], "log")
        self.assertNotIn("--max-count", captured["args"])
        self.assertIn("android13-5.15-2026-03_r16..HEAD", captured["args"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sha"], "abc123")

    def test_collect_uses_crash_files_not_full_history(self):
        calls = []

        def fake_run_git(_repo, args, timeout=None):
            cmd = list(args)
            calls.append(cmd)
            if "--" in cmd:
                return "ccc\x01touch crash file\nmm/file.c\n"
            if "--grep" in cmd:
                return "bbb\x01fix panic in foo_bar\nmm/file.c\n"
            raise AssertionError(f"unexpected git {cmd}")

        resolved = {
            "tips": [{
                "ref": "aosp/android16-6.18",
                "sha": "headsha",
                "branch": "android16-6.18",
                "start": "android13-tag",
            }],
            "end_ref": "aosp/android16-6.18",
            "end_sha": "headsha",
            "count": 1200,
            "series": "android13-5.15",
            "fetched": True,
            "empty_reason": "",
            "fetched_branches": ["android16-6.18"],
            "fetch_source": "https://android.googlesource.com/kernel/common",
            "branches": ["android16-6.18", "android13-5.15"],
        }
        with patch(
            "web_app.crash_fix_search.resolve_community_search_tips",
            return_value=resolved,
        ), patch(
            "web_app.crash_fix_search._run_git", fake_run_git,
        ):
            ordered, meta = collect_fix_candidates(
                "/repo",
                "android13-tag",
                crash_analysis={
                    "crash_files": ["mm/file.c"],
                    "crash_function": "foo_bar",
                },
            )

        log_cmds = [c for c in calls if c[:1] == ["log"]]
        self.assertTrue(log_cmds)
        rev = "android13-tag..headsha"
        for cmd in log_cmds:
            self.assertTrue("--" in cmd or "--grep" in cmd, cmd)
            self.assertIn(rev, cmd)
            if "--grep" in cmd:
                self.assertLess(cmd.index("--grep"), cmd.index(rev))
            if "--" in cmd:
                self.assertGreater(cmd.index("--"), cmd.index(rev))
        self.assertEqual({c["sha"] for c in ordered}, {"ccc", "bbb"})
        self.assertEqual(ordered[0]["sha"], "bbb")
        self.assertEqual(meta["commits_after_tag"], 1200)
        self.assertEqual(meta["file_touching"], 1)
        self.assertEqual(meta["strategy"], "community_files_and_symbols")
        self.assertEqual(meta["search_to_ref"], "aosp/android16-6.18")
        self.assertEqual(meta["search_to_rev"], "headsha")

    def test_collect_parses_files_from_crash_log(self):
        resolved = {
            "tips": [{
                "ref": "HEAD",
                "sha": "head",
                "branch": "HEAD",
                "start": "tag",
            }],
            "end_ref": "HEAD",
            "end_sha": "head",
            "count": 3,
            "series": "",
            "fetched": False,
            "empty_reason": "",
            "fetched_branches": [],
            "fetch_source": "",
            "branches": [],
        }
        with patch(
            "web_app.crash_fix_search.resolve_community_search_tips",
            return_value=resolved,
        ), patch(
            "web_app.crash_fix_search._run_git",
            return_value="aaa\x01fix foo\nmm/oops.c\n",
        ):
            ordered, meta = collect_fix_candidates(
                "/repo",
                "tag",
                crash_analysis={},
                crash_log="PC is at foo+0x10/0x20\n[  0.0] foo+0x10/0x20 mm/oops.c:12",
            )
        self.assertEqual(meta["crash_files"], ["mm/oops.c"])
        self.assertEqual([c["sha"] for c in ordered], ["aaa"])

    def test_select_community_branches_includes_newer_kernel(self):
        picked = select_community_branches(
            ["android15-6.6", "android16-6.12", "android16-6.18", "android-mainline"],
            "android16-6.12",
        )
        self.assertEqual(picked, ["android16-6.18", "android16-6.12", "android-mainline"])
        self.assertNotIn("android15-6.6", picked)


class CrashAnalysisModeTests(unittest.TestCase):
    def test_interval_requires_both_tags(self):
        crash_id, err = start_crash_analysis("", "to-tag", "log", mode="interval")
        self.assertEqual(crash_id, "")
        self.assertIn("from_tag", err or "")

    def test_current_tag_requires_tag(self):
        crash_id, err = start_crash_analysis("", "", "log", mode="current_tag")
        self.assertEqual(crash_id, "")
        self.assertIn("GKI tag", err or "")

    def test_current_tag_starts_without_from_tag(self):
        with patch("web_app.crash_analysis_service.create_crash_analysis") as create, patch(
            "web_app.crash_analysis_service.threading.Thread"
        ) as thread:
            thread.return_value.start = lambda: None
            crash_id, err = start_crash_analysis(
                "", "android13-5.15-2026-03_r16", "panic log", mode="current_tag",
            )
        self.assertIsNone(err)
        self.assertTrue(crash_id)
        args = thread.call_args.kwargs.get("args") or thread.call_args[0]
        if not isinstance(args, tuple):
            args = thread.call_args[1]["args"]
        self.assertEqual(args[1], "")
        self.assertEqual(args[2], "android13-5.15-2026-03_r16")
        self.assertEqual(args[4], "current_tag")
        create.assert_called_once()
        self.assertEqual(create.call_args[0][1], "")
        self.assertEqual(create.call_args[0][2], "android13-5.15-2026-03_r16")

    def test_current_tag_report_hides_suspected_patches(self):
        html = _build_crash_report(
            crash_id="abc123",
            from_tag="",
            to_tag="android13-5.15-2026-03_r16",
            crash_log="panic",
            crash_summary={
                "analysis_mode": "current_tag",
                "crash_type": "panic",
                "crash_function": "foo",
                "crash_module": "mm",
                "fix_search": {
                    "search_from_tag": "android13-5.15-2026-03_r16",
                    "commits_after_tag": 1200,
                    "candidates": 8,
                },
            },
            is_caused=False,
            confidence="中",
            explanation="只查社区修复",
            suspected=[{"sha": "deadbeef", "title": "should not show", "reason": "x"}],
            fix_commits=[],
            recommendations={},
            total_patches=0,
        )
        self.assertNotIn("疑似问题 Patch", html)
        self.assertIn("查社区修复", html)
        self.assertIn("未在当前 Tag 至社区/谷歌最新提交中找到", html)
        self.assertIn("1200", html)


if __name__ == "__main__":
    unittest.main()
