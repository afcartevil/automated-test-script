"""Local mount paths must keep Windows drive letters, not resolve to UNC."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.job_path_mapping import persist_local_mount_path


class PersistLocalMountPathTests(unittest.TestCase):
    def test_keeps_windows_drive_letter(self):
        raw = r"Z:\KM9_before\kernel-5.15"
        with patch.object(Path, "resolve", autospec=True) as resolve:
            resolve.side_effect = AssertionError("must not resolve mapped drive letters")
            out = persist_local_mount_path(raw)
        self.assertTrue(out.startswith("Z:"), out)
        self.assertNotIn("10.", out)
        self.assertFalse(out.startswith("\\\\"))

    def test_strips_whitespace(self):
        self.assertEqual(persist_local_mount_path("  Z:\\KM9_before\\kernel-5.15  "), persist_local_mount_path("Z:\\KM9_before\\kernel-5.15"))

    def test_empty(self):
        self.assertEqual(persist_local_mount_path("  "), "")


if __name__ == "__main__":
    unittest.main()
