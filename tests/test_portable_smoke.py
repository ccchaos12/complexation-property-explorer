from __future__ import annotations

import gc
import os
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

from complexation_explorer.database import (
    SearchFilters,
    count_constants,
    get_database_summary,
    search_constants,
)
from complexation_explorer.formatting import data_note, display_record_id
from tests.support import create_test_database


class PortableDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = create_test_database(
            Path(self.temporary_directory.name) / "fixture.db"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_numeric_ranges_and_numeric_only(self):
        filters = SearchFilters(
            value_type="K",
            value_min=10,
            value_max=20,
            temperature_c_min=20,
            temperature_c_max=30,
            ionic_strength_min=0.05,
            ionic_strength_max=0.2,
            numeric_only=True,
        )
        rows = search_constants(filters, self.database_path, limit=10)
        self.assertEqual(
            [row["record_id"] for row in rows],
            ["NIST_SRD46:CONSTANT:100001"],
        )

        with self.assertRaisesRegex(ValueError, "minimum cannot exceed maximum"):
            count_constants(
                SearchFilters(value_type="K", value_min=20, value_max=10),
                self.database_path,
            )

    def test_reaction_filter_and_human_data_note(self):
        filters = SearchFilters(
            value_type="K",
            reaction_types=("complex_1_2",),
        )
        rows = search_constants(filters, self.database_path, limit=10)
        self.assertEqual(count_constants(filters, self.database_path), 1)
        self.assertEqual(rows[0]["reaction_type"], "complex_1_2")
        self.assertEqual(
            data_note(rows[0]),
            "Source value uses non-numeric notation",
        )

    def test_source_namespace_prevents_short_id_collisions(self):
        summary = get_database_summary(self.database_path)
        self.assertEqual(summary["source_count"], 2)
        self.assertEqual(summary["schema_version"], "1")
        self.assertEqual(len(summary["database_sha256"]), 64)
        self.assertNotEqual(
            display_record_id(
                "NIST_SRD46:CONSTANT:100001",
                "NIST_SRD46",
                include_source=True,
            ),
            display_record_id(
                "LOCAL_XLSX:CONSTANT:100001",
                "LOCAL_XLSX",
                include_source=True,
            ),
        )
        self.assertEqual(
            display_record_id(
                "NIST_SRD46:CONSTANT:100001",
                "NIST_SRD46",
                include_source=True,
            ),
            "NIST · 100001",
        )


class StreamlitSmokeTests(unittest.TestCase):
    def test_app_renders_compact_results_without_exceptions(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest("Streamlit testing API is unavailable")

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = create_test_database(
                Path(temporary_directory) / "fixture.db"
            )
            app_path = Path(__file__).resolve().parents[1] / "app.py"
            with patch.dict(
                os.environ,
                {"COMPLEXATION_DB_PATH": str(database_path)},
            ):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    app = AppTest.from_file(str(app_path)).run(timeout=30)
                    self.assertEqual(list(app.exception), [])
                    self.assertGreaterEqual(len(app.dataframe), 1)
                    self.assertEqual(
                        list(app.dataframe[0].value.columns),
                        [
                            "Record ID",
                            "Metal",
                            "Ligand",
                            "Formula",
                            "Equilibrium",
                            "Value",
                            "Temperature (°C)",
                            "Ionic strength",
                        ],
                    )
                    app.toggle[0].set_value(True).run(timeout=30)
                    extended_columns = list(app.dataframe[0].value.columns)
                    self.assertIn("Data note", extended_columns)
                    self.assertNotIn("Quality flags", extended_columns)
                    del app
                    gc.collect()


if __name__ == "__main__":
    unittest.main()
