from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from complexation_explorer.io_utils import readonly_sqlite_uri, require_distinct_paths


class PathSafetyTests(unittest.TestCase):
    def test_readonly_sqlite_uri_encodes_reserved_path_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "constants ?#%.db"
            uri = readonly_sqlite_uri(path)

        self.assertTrue(uri.startswith("file:"))
        self.assertIn("%20", uri)
        self.assertIn("%3F", uri)
        self.assertIn("%23", uri)
        self.assertIn("%25", uri)
        self.assertTrue(uri.endswith("?mode=ro"))

    def test_colliding_input_and_output_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "same.db"
            with self.assertRaisesRegex(ValueError, "Paths must be distinct"):
                require_distinct_paths(source=path, output=path)


if __name__ == "__main__":
    unittest.main()
