"""同文案标题+按钮时，tap 应优先可点 Button。"""

from __future__ import annotations

import unittest

from utils.nl_ui.actions import _pick_best_text_tap_target


TITLE_AND_BUTTON_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" clickable="false">
    <node index="0" class="android.widget.TextView" text="校准" bounds="[40,120][200,200]" clickable="false" enabled="true" displayed="true"/>
    <node index="1" class="android.widget.Button" text="校准" bounds="[300,1800][780,1960]" clickable="true" enabled="true" displayed="true"/>
  </node>
</hierarchy>
"""


class TapPreferClickableTest(unittest.TestCase):
    def test_prefers_button_over_title(self) -> None:
        picked = _pick_best_text_tap_target(TITLE_AND_BUTTON_XML, text="校准")
        self.assertIsNotNone(picked)
        assert picked is not None
        tap_node, score = picked
        self.assertEqual(tap_node.attrib.get("class"), "android.widget.Button")
        self.assertEqual(tap_node.attrib.get("clickable"), "true")
        self.assertGreater(score, 0)
        bounds = tap_node.attrib.get("bounds") or ""
        self.assertIn("1800", bounds)

    def test_button_child_text_resolves_to_button(self) -> None:
        xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node class="android.widget.TextView" text="校准" bounds="[40,120][200,200]" clickable="false" enabled="true" displayed="true"/>
  <node class="android.widget.Button" bounds="[300,1800][780,1960]" clickable="true" enabled="true" displayed="true">
    <node class="android.widget.TextView" text="校准" bounds="[320,1820][760,1940]" clickable="false" enabled="true" displayed="true"/>
  </node>
</hierarchy>
"""
        picked = _pick_best_text_tap_target(xml, text="校准")
        self.assertIsNotNone(picked)
        assert picked is not None
        tap_node, _score = picked
        self.assertEqual(tap_node.attrib.get("class"), "android.widget.Button")


if __name__ == "__main__":
    unittest.main()
