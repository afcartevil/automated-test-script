"""format_step_summary 单元测试。"""

from __future__ import annotations

import unittest

from utils.nl_ui.step_format import format_step_summary


class FormatStepSummaryTest(unittest.TestCase):
    def test_tap_and_assert(self) -> None:
        self.assertEqual(format_step_summary({"op": "tap_text", "text": "校准"}), "tap_text 校准")
        self.assertEqual(format_step_summary({"op": "assert_text", "text": "传感器"}), "assert_text 传感器")
        self.assertEqual(
            format_step_summary({"op": "assert_text", "text": "错误", "present": False}),
            "assert_text 不应出现 错误",
        )

    def test_wait_until_and_dial_keys(self) -> None:
        self.assertEqual(
            format_step_summary({"op": "wait_until", "condition": "clickable", "text": "校准"}),
            "wait_until clickable 校准",
        )
        self.assertEqual(format_step_summary({"op": "dial_keys", "keys": "*#888#"}), "dial_keys *#888#")
        self.assertEqual(
            format_step_summary({"op": "tap_rid", "rid": "dialpad_floating_action_button"}),
            "tap_rid dialpad_floating_action_button",
        )


if __name__ == "__main__":
    unittest.main()
