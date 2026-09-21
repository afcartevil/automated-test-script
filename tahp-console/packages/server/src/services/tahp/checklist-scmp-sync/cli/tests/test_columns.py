import unittest

from checklist_scmp_sync.columns import (
    col_letter,
    find_target_columns,
    should_skip_sheet,
)


class ColLetterTests(unittest.TestCase):
    def test_basic_letters(self):
        self.assertEqual(col_letter(1), "A")
        self.assertEqual(col_letter(26), "Z")
        self.assertEqual(col_letter(27), "AA")
        self.assertEqual(col_letter(43), "AQ")


class FindTargetColumnsTests(unittest.TestCase):
    def test_audio_like_headers(self):
        rows = [
            [
                "一级SF",
                "特性编码",
                "关联属性名",
                "在研项目",
                "",
                "",
            ],
            [
                "",
                "",
                "",
                "此特性是否支持",
                "检查结果",
                "备注",
            ],
        ]
        found = find_target_columns(rows)
        self.assertEqual(found.code_index, 1)
        self.assertEqual(found.support_index, 3)
        self.assertEqual(found.remark_index, 5)

    def test_missing_code_column_raises(self):
        with self.assertRaises(ValueError):
            find_target_columns([["一级SF", "此特性是否支持", "备注"]])


class ShouldSkipSheetTests(unittest.TestCase):
    def test_skip_changelog(self):
        self.assertTrue(should_skip_sheet("变更记录", hidden=False))

    def test_skip_hidden(self):
        self.assertTrue(should_skip_sheet("Audio", hidden=True))

    def test_skip_deprecated_name(self):
        self.assertTrue(should_skip_sheet("WCN驱动（废弃）", hidden=False))

    def test_keep_normal(self):
        self.assertFalse(should_skip_sheet("Audio", hidden=False))

    def test_include_hidden_keeps_hidden_and_deprecated(self):
        self.assertFalse(
            should_skip_sheet("WCN框架（废弃）", hidden=True, include_hidden=True)
        )


if __name__ == "__main__":
    unittest.main()
