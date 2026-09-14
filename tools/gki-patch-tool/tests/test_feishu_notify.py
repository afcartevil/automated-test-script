"""Feishu task-finished cards for analysis / crash / upgrade."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.feishu_service import (
    _crash_notify_card,
    _task_notify_card,
    _upgrade_notify_card,
    notify_upgrade_finished,
)


def _card_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


class FeishuNotifyCardTests(unittest.TestCase):
    def test_analysis_completed_keeps_checklist_button(self):
        payload = _task_notify_card(
            {
                "id": "task1",
                "repo": "common",
                "from_tag": "a",
                "to_tag": "b",
                "total": 12,
                "feishu_checklist_url": "https://feishu.cn/sheets/x",
            },
            status="completed",
        )
        self.assertEqual(payload["card"]["header"]["title"]["content"], "GKI 分析任务完成")
        self.assertEqual(payload["card"]["header"]["template"], "green")
        self.assertIn("打开验收表格", _card_text(payload))

    def test_crash_completed_includes_suspected_count(self):
        payload = _crash_notify_card(
            {
                "id": "crash1",
                "from_tag": "android13-5.15-2025-09_r9",
                "to_tag": "android13-5.15-2026-03_r16",
                "is_caused_by_merge": 1,
                "suspected_patches": [{"sha": "abc"}, {"sha": "def"}],
                "fix_commits": [],
                "elapsed_seconds": 42,
                "crash_summary": {
                    "confidence": 0.9,
                    "analysis_mode": "interval",
                    "crash_type": "NULL",
                    "crash_function": "foo_bar",
                },
            },
            status="completed",
        )
        self.assertEqual(payload["card"]["header"]["title"]["content"], "GKI 故障诊断完成")
        text = _card_text(payload)
        self.assertIn("合入引起", text)
        self.assertIn("疑似引入", text)
        self.assertIn("社区修复", text)
        self.assertIn("2", text)
        self.assertIn("42s", text)
        self.assertIn("foo_bar", text)

    def test_crash_completed_includes_community_fix_patches(self):
        payload = _crash_notify_card(
            {
                "id": "4d7faa09dd8e",
                "from_tag": "",
                "to_tag": "android16-6.12-2025-09_r8",
                "is_caused_by_merge": 0,
                "suspected_patches": [],
                "fix_commits": [
                    {
                        "sha": "deadbeefcafebabe",
                        "title": "f2fs: fix insert extent tree infinite loop",
                        "confidence": "高",
                    },
                    {
                        "sha": "1122334455667788",
                        "title": "f2fs: return NULL after WARN",
                        "confidence": "中",
                    },
                ],
                "elapsed_seconds": 299,
                "crash_summary": {
                    "confidence": "中",
                    "analysis_mode": "current_tag",
                    "crash_type": "HWT",
                    "crash_function": "__insert_extent_tree",
                    "latest_compare": {"latest_status": "likely_fixed"},
                },
            },
            status="completed",
        )
        text = _card_text(payload)
        self.assertIn("当前 Tag", text)
        self.assertIn("android16-6.12-2025-09_r8", text)
        self.assertNotIn("? →", text)
        self.assertNotIn("合入引起", text)
        self.assertIn("社区修复", text)
        self.assertIn("修复 Patch", text)
        self.assertIn("deadbeefcafe", text)
        self.assertIn("android.googlesource.com/kernel/common/+/deadbeefcafebabe", text)
        self.assertIn("insert extent tree", text)
        self.assertIn("最新已避开", text)
        self.assertIn("__insert_extent_tree", text)

    def test_crash_failed_title(self):
        payload = _crash_notify_card(
            {"id": "crash2", "from_tag": "a", "to_tag": "b", "error_msg": "no log"},
            status="failed",
        )
        self.assertEqual(payload["card"]["header"]["title"]["content"], "GKI 故障诊断失败")
        self.assertEqual(payload["card"]["header"]["template"], "red")
        self.assertIn("no log", _card_text(payload))

    def test_upgrade_completed_and_failed(self):
        ok = _upgrade_notify_card(
            {
                "id": "job1",
                "target_repo_dir": "/kernel/common",
                "from_tag": "a",
                "to_tag": "b",
                "phase": "done",
                "commit_sha": "0123456789abcdef",
            },
            status="completed",
        )
        self.assertEqual(ok["card"]["header"]["title"]["content"], "GKI 入库任务完成")
        self.assertIn("0123456789ab", _card_text(ok))

        fail = _upgrade_notify_card(
            {
                "id": "job2",
                "target_repo_dir": "/kernel/common",
                "from_tag": "a",
                "to_tag": "b",
                "phase": "apply",
                "error_msg": "git apply 失败",
            },
            status="failed",
        )
        self.assertEqual(fail["card"]["header"]["title"]["content"], "GKI 入库任务失败")
        self.assertIn("git apply 失败", _card_text(fail))

    def test_upgrade_notify_skips_intermediate_status(self):
        job = {"id": "job3", "status": "conflicts"}
        with mock.patch("web_app.database.get_upgrade_job", return_value=job):
            self.assertIsNone(notify_upgrade_finished("job3", status="conflicts"))


if __name__ == "__main__":
    unittest.main()
