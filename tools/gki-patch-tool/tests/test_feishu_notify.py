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
                "elapsed_seconds": 42,
                "crash_summary": {"confidence": 0.9},
            },
            status="completed",
        )
        self.assertEqual(payload["card"]["header"]["title"]["content"], "GKI 故障诊断完成")
        text = _card_text(payload)
        self.assertIn("合入引起", text)
        self.assertIn("2", text)
        self.assertIn("42s", text)

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
