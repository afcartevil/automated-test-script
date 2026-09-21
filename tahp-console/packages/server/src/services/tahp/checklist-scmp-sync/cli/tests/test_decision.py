import unittest

from checklist_scmp_sync.decision import decide_row_update


class DecideRowUpdateTests(unittest.TestCase):
    def test_all_supported(self):
        result = decide_row_update({"OP": "1", "RU": "1", "EU": "1"})
        self.assertEqual(result.support, "支持")
        self.assertEqual(result.remark, "")
        self.assertTrue(result.write_support)

    def test_all_unsupported(self):
        result = decide_row_update({"OP": "0", "RU": "0", "EU": "0"})
        self.assertEqual(result.support, "不支持")
        self.assertEqual(result.remark, "")
        self.assertTrue(result.write_support)

    def test_partial_supported_lists_markets(self):
        result = decide_row_update({"OP": "1", "RU": "0", "EU": "1", "TR": "0"})
        self.assertEqual(result.support, "支持")
        self.assertEqual(result.remark, "部分市场支持：EU, OP")
        self.assertTrue(result.write_support)

    def test_missing_feature(self):
        result = decide_row_update(None)
        self.assertIsNone(result.support)
        self.assertEqual(result.remark, "特性编码不存在")
        self.assertFalse(result.write_support)

    def test_empty_market_map_is_missing(self):
        result = decide_row_update({})
        self.assertEqual(result.remark, "特性编码不存在")
        self.assertFalse(result.write_support)


if __name__ == "__main__":
    unittest.main()
