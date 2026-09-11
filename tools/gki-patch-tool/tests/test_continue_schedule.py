"""Continue-after-conflicts must return immediately and only accept conflicts jobs."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.upgrade_service import schedule_continue_after_conflicts


class ContinueScheduleTests(unittest.TestCase):
    def test_rejects_non_conflicts_status(self):
        with patch("web_app.upgrade_service.get_upgrade_job", return_value={"status": "build_failed"}):
            ok, msg = schedule_continue_after_conflicts("job-1")
        self.assertFalse(ok)
        self.assertIn("conflicts", msg)

    def test_rejects_missing_job(self):
        with patch("web_app.upgrade_service.get_upgrade_job", return_value=None):
            ok, msg = schedule_continue_after_conflicts("job-missing")
        self.assertFalse(ok)
        self.assertIn("不存在", msg)
