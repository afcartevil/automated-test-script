import unittest

from checklist_scmp_sync.parse import (
    code_cell_status,
    extract_feature_codes,
    normalize_tos_version,
    parse_document_title,
)


class ParseDocumentTitleTests(unittest.TestCase):
    def test_sample_checklist_title(self):
        parsed = parse_document_title("X6879-tOS17 全功能特性checklist_V2.5 副本")
        self.assertEqual(parsed.project, "X6879")
        self.assertEqual(parsed.tos_version, "17.0.0")

    def test_later_renamed_title_still_extracts_tokens(self):
        parsed = parse_document_title("【底软】X6879 tOS16.3 检查表 V3")
        self.assertEqual(parsed.project, "X6879")
        self.assertEqual(parsed.tos_version, "16.3.0")

    def test_already_dotted_tos_version(self):
        parsed = parse_document_title("X6880-tOS16.3.0-checklist")
        self.assertEqual(parsed.project, "X6880")
        self.assertEqual(parsed.tos_version, "16.3.0")

    def test_missing_project_raises(self):
        with self.assertRaises(ValueError):
            parse_document_title("tOS17 全功能特性checklist")

    def test_missing_tos_raises(self):
        with self.assertRaises(ValueError):
            parse_document_title("X6879 全功能特性checklist_V2.5")


class NormalizeTosVersionTests(unittest.TestCase):
    def test_major_only_pads_to_three_parts(self):
        self.assertEqual(normalize_tos_version("17"), "17.0.0")

    def test_minor_pads_patch(self):
        self.assertEqual(normalize_tos_version("16.3"), "16.3.0")

    def test_full_version_kept(self):
        self.assertEqual(normalize_tos_version("16.3.0"), "16.3.0")


class ExtractFeatureCodesTests(unittest.TestCase):
    def test_single_sf_code(self):
        primary, extras = extract_feature_codes("SF-202507-001364")
        self.assertEqual(primary, "SF-202507-001364")
        self.assertEqual(extras, [])

    def test_sr_code(self):
        primary, extras = extract_feature_codes("SR-202603-002561")
        self.assertEqual(primary, "SR-202603-002561")
        self.assertEqual(extras, [])

    def test_multiple_codes_keep_first(self):
        primary, extras = extract_feature_codes(
            "SF-202508-000072\nSF-202507-001905"
        )
        self.assertEqual(primary, "SF-202508-000072")
        self.assertEqual(extras, ["SF-202507-001905"])

    def test_empty_or_slash_is_none(self):
        self.assertEqual(extract_feature_codes(""), (None, []))
        self.assertEqual(extract_feature_codes("/"), (None, []))
        self.assertEqual(extract_feature_codes("\\"), (None, []))

    def test_wrapped_code_with_newline_inside_digits(self):
        primary, extras = extract_feature_codes("SF-202507-00\n8776")
        self.assertEqual(primary, "SF-202507-008776")
        self.assertEqual(extras, [])

    def test_wrapped_code_mid_serial_still_unique(self):
        primary, extras = extract_feature_codes("SF-202507-00\n2610")
        self.assertEqual(primary, "SF-202507-002610")
        self.assertEqual(extras, [])

    def test_short_serial_is_kept_as_is(self):
        primary, extras = extract_feature_codes("SF-202602-00101")
        self.assertEqual(primary, "SF-202602-00101")
        self.assertEqual(extras, [])

    def test_short_serial_with_five_digits(self):
        primary, extras = extract_feature_codes("SF-202602-00125")
        self.assertEqual(primary, "SF-202602-00125")
        self.assertEqual(extras, [])

    def test_code_without_second_hyphen(self):
        primary, extras = extract_feature_codes("SF-20260200101")
        self.assertEqual(primary, "SF-20260200101")
        self.assertEqual(extras, [])

    def test_sf_without_digits_is_not_a_code(self):
        self.assertEqual(extract_feature_codes("SF-"), (None, []))
        self.assertEqual(extract_feature_codes("SF-abc"), (None, []))

    def test_code_cell_status_categories(self):
        self.assertEqual(code_cell_status("SF-202507-001364"), "ok")
        self.assertEqual(code_cell_status("SF-202507-00\n8776"), "ok")
        self.assertEqual(code_cell_status("SF-202602-00101"), "ok")
        self.assertEqual(code_cell_status("/"), "empty")
        self.assertEqual(code_cell_status("待补充"), "placeholder")
        self.assertEqual(code_cell_status("SF-"), "invalid_format")
        self.assertEqual(code_cell_status("OS16"), "other")


if __name__ == "__main__":
    unittest.main()
