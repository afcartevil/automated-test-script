"""tap_rid 按 resource-id 点击。"""

from __future__ import annotations

import unittest

from utils.nl_ui.actions import _pick_best_rid_tap_target
from utils.nl_ui.schema import normalize_plan
from utils.nl_ui.step_format import format_step_summary


DIAL_FAB_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" clickable="false">
  <node class="android.widget.EditText" text="18676785952" bounds="[60,200][1020,320]" clickable="false" enabled="true" displayed="true"/>
  <node class="com.google.android.material.floatingactionbutton.FloatingActionButton"
        resource-id="com.google.android.dialer:id/dialpad_floating_action_button"
        bounds="[900,2000][1020,2120]" clickable="true" enabled="true" displayed="true"/>
  </node>
</hierarchy>
"""


class TapRidTest(unittest.TestCase):
    def test_format_and_schema(self) -> None:
        step = {"op": "tap_rid", "rid": "dialpad_floating_action_button"}
        self.assertEqual(format_step_summary(step), "tap_rid dialpad_floating_action_button")
        plan = normalize_plan({
            "executable": True,
            "steps": [
                {"op": "dial_keys", "keys": "18676785952"},
                step,
                {"op": "assert_text", "text": "通话中"},
            ],
        })
        self.assertEqual(plan["steps"][1]["rid"], "dialpad_floating_action_button")

    def test_pick_floating_action_button_by_suffix(self) -> None:
        picked = _pick_best_rid_tap_target(DIAL_FAB_XML, "dialpad_floating_action_button")
        self.assertIsNotNone(picked)
        assert picked is not None
        tap_node, score = picked
        self.assertEqual(
            tap_node.attrib.get("resource-id"),
            "com.google.android.dialer:id/dialpad_floating_action_button",
        )
        self.assertEqual(tap_node.attrib.get("clickable"), "true")
        self.assertGreater(score, 0)
        bounds = tap_node.attrib.get("bounds") or ""
        self.assertIn("2000", bounds)


if __name__ == "__main__":
    unittest.main()
