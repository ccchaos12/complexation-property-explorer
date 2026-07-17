from __future__ import annotations

import unittest

from complexation_explorer.ui import clamp_page, selected_record_id_from_rows


class PaginationTests(unittest.TestCase):
    def test_page_is_clamped_to_one_based_range(self):
        self.assertEqual(clamp_page(0, 12), 1)
        self.assertEqual(clamp_page(7, 12), 7)
        self.assertEqual(clamp_page(99, 12), 12)

    def test_empty_result_set_still_has_page_one(self):
        self.assertEqual(clamp_page(5, 0), 1)


class DataframeSelectionTests(unittest.TestCase):
    def test_selected_row_resolves_to_record_id(self):
        rows = [{"record_id": "A"}, {"record_id": "B"}]
        self.assertEqual(selected_record_id_from_rows(rows, [1]), "B")

    def test_empty_or_stale_selection_is_ignored(self):
        rows = [{"record_id": "A"}]
        self.assertIsNone(selected_record_id_from_rows(rows, []))
        self.assertIsNone(selected_record_id_from_rows(rows, [5]))


if __name__ == "__main__":
    unittest.main()
