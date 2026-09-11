"""Crash-site source lookup from the local GKI repo."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.crash_source import (
    collect_crash_source,
    collect_source_at_rev,
    format_snippet,
    list_path_commits,
    parse_crash_sites,
    pick_latest_compare_tip,
    resolve_source_path,
)
from web_app.crash_analysis_service import _build_crash_report


class ParseCrashSitesTests(unittest.TestCase):
    def test_extracts_file_line_and_skips_generic_pc(self):
        log = (
            "Unable to handle kernel NULL pointer dereference at virtual address 00000000\n"
            "PC is at panic+0x10/0x20\n"
            "Call trace:\n"
            " foo_bar+0x20/0x80 mm/shmem.c:445\n"
            " kernel BUG at drivers/usb/core/hub.c:1234!\n"
        )
        parsed = parse_crash_sites(log)
        self.assertEqual(parsed["function"], "foo_bar")
        paths = {(item["path"], item["line"]) for item in parsed["files"]}
        self.assertIn(("mm/shmem.c", 445), paths)
        self.assertIn(("drivers/usb/core/hub.c", 1234), paths)

    def test_prefers_pc_function_over_later_frames(self):
        log = "PC is at binder_ioctl+0x40/0x100\n binder_ioctl+0x40/0x100 drivers/android/binder.c:88\n"
        parsed = parse_crash_sites(log)
        self.assertEqual(parsed["function"], "binder_ioctl")

    def test_parses_arm64_pc_with_bracket_address(self):
        log = (
            "Unable to handle kernel NULL pointer dereference at virtual address 0000000000000040\n"
            "pc : [0xffffffe7f81de95c] fuse_iget_backing+0x34/0x13c\n"
            "lr : [0xffffffe7f81eb1dc] fuse_mkdir_backing+0x124/0x174\n"
            "Call trace:\n"
            " dump_backtrace+0xec/0x128\n"
            " fuse_iget_backing+0x34/0x13c\n"
        )
        parsed = parse_crash_sites(log)
        self.assertEqual(parsed["function"], "fuse_iget_backing")

    def test_strips_proc_cwd_common_source_path(self):
        log = "fuse_iget_backing </proc/self/cwd/common/fs/fuse/inode.c:524>\n"
        parsed = parse_crash_sites(log)
        paths = {(item["path"], item["line"]) for item in parsed["files"]}
        self.assertIn(("fs/fuse/inode.c", 524), paths)


class ResolveAndFormatTests(unittest.TestCase):
    def test_resolve_prefers_kernel_tree_prefix(self):
        tree = ["samples/hub.c", "drivers/usb/core/hub.c", "include/linux/hub.h"]
        self.assertEqual(resolve_source_path(tree, "hub.c"), "drivers/usb/core/hub.c")
        self.assertEqual(resolve_source_path(tree, "drivers/usb/core/hub.c"), "drivers/usb/core/hub.c")

    def test_format_snippet_marks_crash_line(self):
        content = "int foo(void)\n{\n\treturn 0;\n}\n"
        formatted = format_snippet(content, highlight_line=3)
        self.assertIn(">     3|", formatted["text"])
        self.assertTrue(formatted["text"].splitlines()[0].startswith(" "))


class CollectCrashSourceTests(unittest.TestCase):
    def test_collects_snippet_from_mocked_git(self):
        file_text = "\n".join([
            "int foo_bar(struct inode *inode)",
            "{",
            "\tstruct shmem_inode_info *info = SHMEM_I(inode);",
            "\treturn info->flags;",
            "}",
        ])

        def fake_git(_repo, args, timeout=None):
            cmd = list(args)
            if cmd[:3] == ["ls-tree", "-r", "--name-only"]:
                return "mm/shmem.c\n"
            if cmd[:1] == ["show"]:
                return file_text
            raise AssertionError(cmd)

        with patch("web_app.crash_source._run_git", fake_git):
            pack = collect_crash_source(
                "/repo",
                "android13-5.15-2026-03_r16",
                "PC is at foo_bar+0x10/0x20\n foo_bar+0x10/0x20 mm/shmem.c:4\n",
            )
        self.assertEqual(len(pack["snippets"]), 1)
        snip = pack["snippets"][0]
        self.assertEqual(snip["path"], "mm/shmem.c")
        self.assertEqual(snip["line"], 4)
        self.assertIn(">     4|", snip["text"])
        self.assertIn("android13-5.15-2026-03_r16", pack["prompt_block"])
        self.assertIn("mm/shmem.c:4", pack["prompt_block"])

    def test_collect_uses_analysis_files_when_log_has_no_path(self):
        file_text = "int foo_bar(void)\n{\n\treturn 0;\n}\n"

        def fake_git(_repo, args, timeout=None):
            cmd = list(args)
            if cmd[:3] == ["ls-tree", "-r", "--name-only"]:
                return "mm/shmem.c\n"
            if cmd[:1] == ["show"]:
                return file_text
            raise AssertionError(cmd)

        with patch("web_app.crash_source._run_git", fake_git):
            pack = collect_crash_source(
                "/repo",
                "android16-6.12-2025-09_r8",
                "PC is at foo_bar+0x10/0x20\nCall trace:\n foo_bar+0x10/0x20\n",
                extra_files=["mm/shmem.c"],
                function="foo_bar",
                source_line=3,
            )
        self.assertEqual(pack["snippets"][0]["path"], "mm/shmem.c")
        self.assertEqual(pack["snippets"][0]["line"], 3)
        self.assertEqual(pack["function"], "foo_bar")
        self.assertFalse(pack["missing_reason"])

    def test_report_includes_source_section(self):
        html = _build_crash_report(
            crash_id="abc",
            from_tag="",
            to_tag="android13-5.15-2026-03_r16",
            crash_log="panic",
            crash_summary={
                "analysis_mode": "current_tag",
                "crash_type": "null-deref",
                "crash_function": "foo_bar",
                "crash_mechanism": "解引用空 info",
                "crash_source_statement": "return info->flags;",
                "source_tag": "android13-5.15-2026-03_r16",
                "crash_source_snippets": [{
                    "path": "mm/shmem.c",
                    "line": 4,
                    "text": ">     4| \treturn info->flags;",
                    "missing": False,
                }],
            },
            is_caused=False,
            confidence="中",
            explanation="x",
            suspected=[],
            fix_commits=[],
            recommendations={},
            total_patches=0,
        )
        self.assertIn("崩溃点源码", html)
        self.assertIn("mm/shmem.c:4", html)
        self.assertIn("return info-&gt;flags;", html)
        self.assertIn("机制说明", html)

    def test_prefer_function_extracts_whole_function(self):
        content = "int other(void) { return 1; }\nint foo_bar(void)\n{\n\treturn 0;\n}\n"
        formatted = format_snippet(content, function="foo_bar", prefer_function=True)
        self.assertIn("foo_bar", formatted["text"])
        self.assertNotIn("other", formatted["text"])

    def test_pick_latest_compare_tip_prefers_same_series(self):
        tip = pick_latest_compare_tip({
            "series": "android13-5.15",
            "tips": [
                {"branch": "android16-6.18", "ref": "aosp/android16-6.18", "sha": "newer"},
                {"branch": "android13-5.15", "ref": "aosp/android13-5.15", "sha": "same"},
            ],
        })
        self.assertEqual(tip["sha"], "same")

    def test_collect_source_at_rev_uses_function_body(self):
        latest = "\n".join([
            "int foo_bar(struct inode *inode)",
            "{",
            "\tif (!inode)",
            "\t\treturn -EINVAL;",
            "\treturn 0;",
            "}",
        ])

        def fake_git(_repo, args, timeout=None):
            cmd = list(args)
            if cmd[:1] == ["show"]:
                return latest
            raise AssertionError(cmd)

        with patch("web_app.crash_source._run_git", fake_git):
            pack = collect_source_at_rev(
                "/repo",
                "aosp/android13-5.15",
                [{"path": "mm/shmem.c", "line": 4, "function": "foo_bar"}],
                function="foo_bar",
            )
        self.assertEqual(len(pack["snippets"]), 1)
        self.assertIn("return -EINVAL", pack["snippets"][0]["text"])
        self.assertFalse(pack["snippets"][0]["missing"])

    def test_list_path_commits_attaches_file_diff(self):
        def fake_git(_repo, args, timeout=None):
            cmd = list(args)
            if cmd[:1] == ["log"] and any(str(a).startswith("-L:") for a in cmd):
                return "abc123\x01fix null deref in foo_bar\n"
            if cmd[:1] == ["show"]:
                return "@@ -1 +1 @@\n-return info->flags;\n+if (!info) return 0;\n"
            raise AssertionError(cmd)

        with patch("web_app.crash_source._run_git", fake_git):
            rows = list_path_commits(
                "/repo", "tag", "head", ["mm/shmem.c"], function="foo_bar",
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sha"], "abc123")
        self.assertIn("if (!info)", rows[0]["diff"])
        self.assertEqual(rows[0]["via"], "function")

    def test_report_includes_latest_compare(self):
        html = _build_crash_report(
            crash_id="abc",
            from_tag="",
            to_tag="android13-5.15-2026-03_r16",
            crash_log="panic",
            crash_summary={
                "analysis_mode": "current_tag",
                "crash_type": "null-deref",
                "crash_function": "foo_bar",
                "latest_compare": {
                    "latest_status": "likely_fixed",
                    "latest_ref": "aosp/android13-5.15",
                    "summary": "最新对 inode 做了空指针检查",
                    "fix_evidence": "if (!inode) return -EINVAL",
                },
                "latest_source_snippets": [{
                    "path": "mm/shmem.c",
                    "text": "if (!inode) return -EINVAL;",
                    "missing": False,
                }],
            },
            is_caused=False,
            confidence="中",
            explanation="x",
            suspected=[],
            fix_commits=[{
                "sha": "abc123def",
                "title": "shmem: fix null inode",
                "fix_type": "fix",
                "confidence": "高",
                "reason": "补了 NULL 检查",
                "via": "source_diff",
            }],
            recommendations={},
            total_patches=0,
        )
        self.assertIn("对照社区最新源码", html)
        self.assertIn("最新源码已避开该崩溃路径", html)
        self.assertIn("源码 diff", html)
        self.assertIn("if (!inode) return -EINVAL", html)


class FunctionGrepAndExtractTests(unittest.TestCase):
    def test_collect_greps_nested_c_file_by_function(self):
        file_text = "\n".join([
            "struct inode *fuse_iget_backing(struct super_block *sb,",
            "\t\t\t\tstruct inode *backing_inode)",
            "{",
            "\treturn backing_inode;",
            "}",
        ])
        tag = "android16-6.12-2025-09_r8"

        def fake_git(_repo, args, timeout=None):
            cmd = list(args)
            if cmd[:1] == ["ls-tree"]:
                raise AssertionError("function-only lookup should not list the whole tree")
            if cmd[:1] == ["grep"]:
                self.assertIn("-F", cmd)
                self.assertNotIn("*.c", cmd)
                self.assertIn("fuse_iget_backing", cmd)
                return f"{tag}:fs/fuse/inode.c:1:struct inode *fuse_iget_backing(struct super_block *sb,\n"
            if cmd[:1] == ["show"]:
                self.assertIn(f"{tag}:fs/fuse/inode.c", cmd)
                return file_text
            raise AssertionError(cmd)

        with patch("web_app.crash_source._run_git", fake_git):
            pack = collect_crash_source(
                "/repo",
                tag,
                "pc : [0xffffffe7f81de95c] fuse_iget_backing+0x34/0x13c\n"
                "Call trace:\n dump_backtrace+0xec/0x128\n fuse_iget_backing+0x34/0x13c\n",
            )
        self.assertFalse(pack["missing_reason"])
        self.assertEqual(pack["function"], "fuse_iget_backing")
        self.assertEqual(pack["snippets"][0]["path"], "fs/fuse/inode.c")
        self.assertIn("fuse_iget_backing", pack["snippets"][0]["text"])

    def test_collect_prefers_definition_over_call_sites(self):
        file_text = "\n".join([
            "struct inode *fuse_iget_backing(struct super_block *sb,",
            "\t\t\t\tstruct inode *backing_inode)",
            "{",
            "\tfuse_fill_attr_from_inode(&attr, get_fuse_inode(backing_inode));",
            "\treturn inode;",
            "}",
        ])
        tag = "android16-6.12-2025-09_r8"
        grep_out = "\n".join([
            f"{tag}:fs/fuse/backing.c:273:\tinode = fuse_iget_backing(dir->i_sb, target_nodeid,",
            f"{tag}:fs/fuse/fuse_i.h:1127:struct inode *fuse_iget_backing(struct super_block *sb,",
            f"{tag}:fs/fuse/inode.c:508:struct inode *fuse_iget_backing(struct super_block *sb, u64 nodeid,",
        ])

        def fake_git(_repo, args, timeout=None):
            cmd = list(args)
            if cmd[:1] == ["ls-tree"]:
                raise AssertionError("function-only lookup should not list the whole tree")
            if cmd[:1] == ["grep"]:
                return grep_out
            if cmd[:1] == ["show"]:
                self.assertIn(f"{tag}:fs/fuse/inode.c", cmd)
                return file_text
            raise AssertionError(cmd)

        with patch("web_app.crash_source._run_git", fake_git):
            pack = collect_crash_source(
                "/repo",
                tag,
                "pc : [0xffff] fuse_iget_backing+0x34/0x13c\n",
            )
        self.assertEqual(pack["snippets"][0]["path"], "fs/fuse/inode.c")
        self.assertEqual(pack["snippets"][0]["line"], 508)
        self.assertIn("fuse_fill_attr_from_inode", pack["snippets"][0]["text"])

    def test_extract_keeps_call_trace_after_register_dump(self):
        from web_app.llm_service import _extract_crash_relevant_sections

        dump_line = (
            "[27687.298965] [T  2546] e8d0: 54000241 b9403688 6b0802ff 54000080 "
            "1400000e 910ee260 942ee69f a9444ff4"
        )
        lines = [
            "[27687.283888] [T  2546] Unable to handle kernel NULL pointer dereference at virtual address 0000000000000040",
            "[27687.298910] [T  2546] pc : [0xffffffe7f81de95c] fuse_iget_backing+0x34/0x13c",
            "[27687.298916] [T  2546] lr : [0xffffffe7f81eb1dc] fuse_mkdir_backing+0x124/0x174",
            "[27687.298962] [T  2546] PC: 0xffffffe7f81de95c:",
        ]
        lines.extend(dump_line for _ in range(180))
        lines.extend([
            "[27687.299387] [T  2546] Call trace:",
            "[27687.299388] [T  2546]  dump_backtrace+0xec/0x128",
            "[27687.299472] [T  2546]  fuse_iget_backing+0x34/0x13c",
            "[27687.299475] [T  2546]  fuse_mkdir_backing+0x124/0x174",
            "[27687.299477] [T  2546]  fuse_mkdir+0x374/0x578",
        ])
        extracted = _extract_crash_relevant_sections("\n".join(lines), max_chars=8000)
        self.assertIn("fuse_iget_backing+0x34/0x13c", extracted)
        self.assertIn("Call trace:", extracted)
        self.assertIn("fuse_mkdir+0x374/0x578", extracted)
        self.assertNotIn("54000241 b9403688", extracted)


if __name__ == "__main__":
    unittest.main()
