from __future__ import annotations

import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DB = (
    PROJECT_ROOT / "data/generated/Complexation_Constants_Unified_rebuilt.db"
)


@unittest.skipUnless(CANONICAL_DB.is_file(), "canonical candidate DB not available")
class CanonicalDatabaseTests(unittest.TestCase):
    def connect(self):
        connection = sqlite3.connect(
            f"file:{CANONICAL_DB.as_posix()}?mode=ro", uri=True
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def test_integrity_and_foreign_keys(self):
        with closing(self.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_source_counts_are_preserved(self):
        with closing(self.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM metal_species").fetchone()[0], 230)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ligands").fetchone()[0], 5_931)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_references").fetchone()[0], 18_392)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM constant_records").fetchone()[0], 90_105)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM ligand_metal_reference_candidates").fetchone()[0],
                80_159,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM ligand_identity_relationships"
                ).fetchone()[0],
                50,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM constant_record_relationships"
                ).fetchone()[0],
                15,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM deduplicated_active_constant_records"
                ).fetchone()[0],
                90_090,
            )

    def test_project_owner_all_verified_policy_is_applied(self):
        with closing(self.connect()) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM verified_constant_records"
                ).fetchone()[0],
                90_105,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM constant_records "
                    "WHERE verification_status <> 'verified'"
                ).fetchone()[0],
                0,
            )

    def test_supplement_records_keep_exact_verified_references(self):
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(c.verified_reference_id IS NOT NULL) AS linked
                FROM constant_records AS c
                JOIN source_versions AS sv
                  ON sv.source_version_id = c.source_version_id
                WHERE sv.source_id = 'SUPPLEMENT'
                """
            ).fetchone()
            self.assertEqual(row["total"], 281)
            self.assertEqual(row["linked"], 281)

    def test_original_and_numeric_values_are_separate(self):
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT reported_value_text, numeric_value, quality_flags_json
                FROM constant_records
                WHERE reported_value_text = '(-0.03)'
                LIMIT 1
                """
            ).fetchone()
            self.assertEqual(row["reported_value_text"], "(-0.03)")
            self.assertIsNone(row["numeric_value"])
            self.assertIn("reported_value_not_strict_numeric", json.loads(row["quality_flags_json"]))

    def test_unified_verified_release_is_not_training_approved(self):
        with closing(self.connect()) as connection:
            release = connection.execute("SELECT * FROM dataset_releases").fetchone()
            manifest = json.loads(release["manifest_json"])
            self.assertEqual(release["release_status"], "reviewed")
            self.assertEqual(release["record_count"], 90_105)
            self.assertEqual(manifest["deduplicated_record_count"], 90_090)
            self.assertEqual(
                manifest["exact_structure_ligand_relationships"], 50
            )
            self.assertEqual(
                manifest["strict_cross_source_duplicate_relationships"], 15
            )
            self.assertEqual(
                manifest["verification_basis"],
                "project_owner_declared_all_verified",
            )
            self.assertFalse(manifest["training_approved"])


if __name__ == "__main__":
    unittest.main()
