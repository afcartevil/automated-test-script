import io
import unittest

from checklist_scmp_sync.progress import emit, make_event_callback


class ProgressEmitTests(unittest.TestCase):
    def test_skipped_when_callback_missing(self):
        emit(None, "start", message="noop")

    def test_callback_receives_event_name(self):
        seen: list[dict] = []
        emit(seen.append, "sheet_start", sheet_name="Audio", index=1, total=2)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["event"], "sheet_start")
        self.assertEqual(seen[0]["sheet_name"], "Audio")
        self.assertEqual(seen[0]["index"], 1)
        self.assertIn("ts", seen[0])

    def test_tee_writes_stdout_and_file(self):
        log_fp = io.StringIO()
        stdout = io.StringIO()
        callback = make_event_callback(to_stdout=True, log_fp=log_fp)
        original = __import__("sys").stdout
        try:
            __import__("sys").stdout = stdout
            callback({"event": "row_skip", "message": "跳过"})
        finally:
            __import__("sys").stdout = original
        self.assertIn("row_skip", stdout.getvalue())
        self.assertIn("row_skip", log_fp.getvalue())


if __name__ == "__main__":
    unittest.main()
