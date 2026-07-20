from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from curation.apply_reviews import REQUIRED_COLUMNS, apply_reviews

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DB = (
    PROJECT_ROOT / "data/generated/Complexation_Constants_Unified_rebuilt.db"
)


@unittest.skipUnless(CANONICAL_DB.is_file(), "canonical candidate DB not available")
class CurationTests(unittest.TestCase):
    def test_verified_decision_creates_separate_curated_database(self):
        with closing(sqlite3.connect(CANONICAL_DB)) as connection:
            record_id, reference_id, original_status = connection.execute(
                """
                SELECT c.record_id, link.reference_id, c.verification_status
                FROM constant_records AS c
                JOIN ligand_metal_reference_candidates AS link
                  ON link.ligand_id = c.ligand_id
                 AND link.metal_species_id = c.metal_species_id
                WHERE link.resolution_status = 'resolved'
                LIMIT 1
                """
            ).fetchone()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decisions = root / "decisions.csv"
            output = root / "curated.db"
            report = root / "report.json"
            with decisions.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
                writer.writeheader()
                writer.writerow(
                    {
                        "review_id": "TEST-REVIEW-001",
                        "record_id": record_id,
                        "decision": "verified",
                        "reviewer": "Automated Test",
                        "reviewed_at_utc": "2026-07-15T20:00:00Z",
                        "reason": "Test-only verification in an isolated temporary copy.",
                        "verified_reference_id": reference_id,
                        "supersedes_record_id": "",
                    }
                )
            result = apply_reviews(CANONICAL_DB, decisions, output, report)
            self.assertEqual(result["validation"]["sqlite_integrity"], "ok")
            self.assertEqual(result["validation"]["foreign_key_errors"], 0)
            self.assertFalse(result["validation"]["training_approved"])
            with closing(sqlite3.connect(output)) as curated:
                status = curated.execute(
                    "SELECT verification_status FROM constant_records WHERE record_id = ?",
                    (record_id,),
                ).fetchone()[0]
                self.assertEqual(status, "verified")
                self.assertEqual(curated.execute("SELECT COUNT(*) FROM review_events").fetchone()[0], 1)
            with closing(sqlite3.connect(CANONICAL_DB)) as canonical:
                status = canonical.execute(
                    "SELECT verification_status FROM constant_records WHERE record_id = ?",
                    (record_id,),
                ).fetchone()[0]
                self.assertEqual(status, original_status)
            report_data = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(report_data["validation"]["local_excel_accessed"])
            self.assertNotIn(str(Path.home()), report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
