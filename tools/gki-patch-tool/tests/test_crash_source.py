"""Crash-site source lookup from the local GKI repo."""
from __future__ import annotations

import os
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

    def test_prepare_crash_log_sends_full_under_threshold(self):
        from web_app import llm_service

        log = "Kernel panic - not syncing\n" + ("noise\n" * 100)
        with patch.dict(os.environ, {
            "GKI_CRASH_LOG_FULL_MAX_CHARS": "50000",
            "GKI_CRASH_LOG_EXTRACT_MAX_CHARS": "30000",
        }, clear=False):
            prepared = llm_service.prepare_crash_log_for_llm(log)
        self.assertEqual(prepared["mode"], "full")
        self.assertEqual(prepared["text"], log)
        self.assertEqual(prepared["sent_chars"], len(log))

    def test_prepare_crash_log_smart_extracts_over_threshold(self):
        from web_app import llm_service

        # Over full threshold, but smart extract should keep panic + nearby lines.
        body = "filler line that is irrelevant\n" * 4000
        crash = (
            "Kernel panic - not syncing: Fatal exception\n"
            "Call trace:\n"
            " foo_bar+0x10/0x20\n"
            " baz+0x1/0x2\n"
        )
        log = body + crash
        with patch.dict(os.environ, {
            "GKI_CRASH_LOG_FULL_MAX_CHARS": "1000",
            "GKI_CRASH_LOG_EXTRACT_MAX_CHARS": "5000",
        }, clear=False):
            prepared = llm_service.prepare_crash_log_for_llm(log)
        self.assertEqual(prepared["mode"], "smart_extract")
        self.assertLess(prepared["sent_chars"], len(log))
        self.assertIn("Kernel panic", prepared["text"])
        self.assertIn("Call trace:", prepared["text"])
        self.assertIn("foo_bar+0x10/0x20", prepared["text"])

    def test_parse_markdown_hwt_analysis_report(self):
        from web_app.llm_service import _try_parse_crash_analysis

        report = """# HWT 死机分析报告（db.fatal.02）

- **异常类型**：**HWT（Hardware Watchdog Timeout，硬件看门狗复位）**

## 一、结论

**本次死机由 F2FS 文件系统 `__insert_extent_tree()` 的已知缺陷直接导致**：
WARN 后缺少 return NULL，CPU6 无法调度。

## 二、死机证据链

`WARNING: CPU: 6 PID: 4540 at fs/f2fs/extent_cache.c:607 __insert_extent_tree+0x7c/0x18c`

## 四、根因分析（代码级）

`fs/f2fs/extent_cache.c` `__insert_extent_tree()`（v6.12.38）
"""
        parsed = _try_parse_crash_analysis(report)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["crash_type"], "HWT")
        self.assertEqual(parsed["crash_function"], "__insert_extent_tree")
        self.assertTrue(
            any("extent_cache.c:607" in f for f in parsed["crash_files"]),
            parsed["crash_files"],
        )
        self.assertIn("__insert_extent_tree", parsed["crash_symbols"])
        self.assertIn("F2FS", parsed["crash_mechanism"] or "")
        self.assertIn("__insert_extent_tree", parsed["crash_mechanism"] or "")
        self.assertEqual(parsed["input_kind"], "analysis_report")

    def test_phase2_prompt_embeds_full_analysis_report(self):
        from web_app import llm_service

        captured = {}

        def fake_call(system, user, config, timeout=300, max_tokens=4096):
            captured["user"] = user
            return (
                "```yaml\nroot_cause:\n  is_caused_by_merge: false\n  confidence: 低\n"
                "  explanation: x\n  causation_type: 无\n  suspected_patches: []\n"
                "recommendations:\n  immediate_actions: a\n  test_suggestions: b\n"
                "  next_steps: c\n```",
                {},
            )

        report = (
            "# HWT 死机分析报告\n\n"
            "- **异常类型**：**HWT**\n\n"
            "## 一、结论\n\n"
            "**本次死机由** F2FS `__insert_extent_tree()` 缺陷导致 UNIQUE_REPORT_MARKER。\n\n"
            "## 二、死机证据链\n\n"
            "at fs/f2fs/extent_cache.c:607 __insert_extent_tree+0x7c/0x18c\n\n"
            "## 四、根因分析\n\n"
            "缺少 return NULL\n"
        )
        analysis = llm_service._try_parse_crash_analysis(report)
        self.assertIsNotNone(analysis)
        analysis["analysis_report_text"] = report
        with patch.object(llm_service, "_call_llm", side_effect=fake_call):
            llm_service.find_suspected_patches(
                crash_analysis=analysis,
                crash_log=report,
                patch_list=[{"sha": "abcd1234", "title": "noop", "files": ["fs/f2fs/extent_cache.c"]}],
                squash_diff="diff --git a/fs/f2fs/extent_cache.c",
                from_tag="A",
                to_tag="B",
            )
        self.assertIn("用户上传的完整分析报告", captured["user"])
        self.assertIn("UNIQUE_REPORT_MARKER", captured["user"])
        self.assertIn("__insert_extent_tree", captured["user"])

    def test_parse_keeps_raw_oops_for_phase1(self):
        from web_app.llm_service import _try_parse_crash_analysis

        lines = [
            f"[{1000 + i}.{i:06d}] Unable to handle kernel NULL pointer dereference"
            if i == 0
            else f"[{1000 + i}.{i:06d}] noise line {i} filler content for density"
            for i in range(20)
        ]
        lines[1] = "[1001.000001] pc : foo_bar+0x10/0x20"
        lines[2] = "[1002.000002] Call trace:"
        lines[3] = "[1003.000003]  foo_bar+0x10/0x20"
        # Mention analysis keywords but remain a dense kernel log.
        lines[4] = "[1004.000004] note: 根因分析 placeholder 死机分析报告 quote"
        self.assertIsNone(_try_parse_crash_analysis("\n".join(lines)))

    def test_parse_yaml_style_analysis_still_works(self):
        from web_app.llm_service import _try_parse_crash_analysis

        text = """
crash_type: NULL pointer
crash_function: fuse_iget_backing
崩溃原因分析: bad pointer in fuse
crash_files:
- fs/fuse/inode.c
crash_symbols:
- fuse_iget_backing
"""
        parsed = _try_parse_crash_analysis(text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["crash_function"], "fuse_iget_backing")
        self.assertEqual(parsed["crash_type"], "NULL pointer")


if __name__ == "__main__":
    unittest.main()
