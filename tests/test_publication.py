from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from curation.apply_reviews import REQUIRED_COLUMNS, apply_reviews
from publication.publish_dataset import (
    EXPORT_COLUMNS,
    _replace_output_pair,
    publish_dataset,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DB = (
    PROJECT_ROOT / "data/generated/Complexation_Constants_Unified_rebuilt.db"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class PublicationOutputTests(unittest.TestCase):
    def test_output_pair_rolls_back_if_second_install_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_target = root / "dataset.csv"
            second_target = root / "manifest.json"
            first_temporary = root / "dataset.tmp"
            second_temporary = root / "manifest.tmp"
            first_target.write_text("old dataset", encoding="utf-8")
            second_target.write_text("old manifest", encoding="utf-8")
            first_temporary.write_text("new dataset", encoding="utf-8")
            second_temporary.write_text("new manifest", encoding="utf-8")
            original_replace = os.replace

            def fail_second_install(source, target):
                if Path(source) == second_temporary:
                    raise OSError("simulated install failure")
                return original_replace(source, target)

            with patch(
                "publication.publish_dataset.os.replace",
                side_effect=fail_second_install,
            ), self.assertRaisesRegex(OSError, "simulated"):
                _replace_output_pair(
                    (
                        (first_temporary, first_target),
                        (second_temporary, second_target),
                    )
                )

            self.assertEqual(first_target.read_text(encoding="utf-8"), "old dataset")
            self.assertEqual(second_target.read_text(encoding="utf-8"), "old manifest")


@unittest.skipUnless(CANONICAL_DB.is_file(), "canonical candidate DB not available")
class PublicationTests(unittest.TestCase):
    def _build_curated_database(self, root: Path) -> tuple[Path, str]:
        with closing(sqlite3.connect(CANONICAL_DB)) as connection:
            record_id, reference_id = connection.execute(
                """
                SELECT c.record_id, link.reference_id
                FROM constant_records AS c
                JOIN ligand_metal_reference_candidates AS link
                  ON link.ligand_id = c.ligand_id
                 AND link.metal_species_id = c.metal_species_id
                JOIN source_references AS r ON r.reference_id = link.reference_id
                WHERE c.numeric_value IS NOT NULL
                  AND link.resolution_status = 'resolved'
                LIMIT 1
                """
            ).fetchone()
        decisions = root / "decisions.csv"
        with decisions.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
            writer.writeheader()
            writer.writerow(
                {
                    "review_id": "TEST-PUBLISH-REVIEW-001",
                    "record_id": record_id,
                    "decision": "verified",
                    "reviewer": "Automated Test",
                    "reviewed_at_utc": "2026-07-15T20:00:00Z",
                    "reason": "Test-only verification in an isolated temporary copy.",
                    "verified_reference_id": reference_id,
                    "supersedes_record_id": "",
                }
            )
        curated = root / "curated.db"
        apply_reviews(CANONICAL_DB, decisions, curated, root / "curation-report.json")
        return curated, record_id

    @staticmethod
    def _write_approval(path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "publication_id": "TEST-ML-RELEASE-001",
                    "approver": "Automated Test Approver",
                    "approved_at_utc": "2026-07-15T21:00:00Z",
                    "purpose": "Verify the publication gate in an isolated test.",
                    "allowed_statuses": ["verified"],
                    "require_numeric_value": True,
                    "require_verified_reference": True,
                }
            ),
            encoding="utf-8",
        )

    def test_verified_numeric_record_is_published_without_database_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            curated, record_id = self._build_curated_database(root)
            approval = root / "approval.json"
            self._write_approval(approval)
            output = root / "dataset.csv"
            manifest_path = root / "dataset.manifest.json"
            before = sha256_file(curated)

            manifest = publish_dataset(
                curated, approval, output, manifest_path
            )

            self.assertEqual(before, sha256_file(curated))
            self.assertTrue(manifest["training_approved"])
            self.assertEqual(manifest["output"]["dataset_sha256"], sha256_file(output))
            self.assertFalse(manifest["local_excel_accessed"])
            terms_by_source = {
                item["source_id"]: item for item in manifest["data_terms"]
            }
            self.assertEqual(
                set(terms_by_source),
                {"NIST_SRD46", "SUPPLEMENT"},
            )
            nist_terms = terms_by_source["NIST_SRD46"]
            self.assertEqual(nist_terms["source_id"], "NIST_SRD46")
            self.assertEqual(nist_terms["doi"], "10.18434/M32154")
            self.assertEqual(
                nist_terms["modification_notice"], "DATA_NOTICE.md"
            )
            self.assertTrue(nist_terms["distribute_notice_with_dataset"])
            with output.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(manifest["output"]["record_count"], len(rows))
            rows_by_id = {row["record_id"]: row for row in rows}
            self.assertEqual(tuple(rows[0]), EXPORT_COLUMNS)
            self.assertIn(record_id, rows_by_id)
            self.assertEqual(
                rows_by_id[record_id]["verification_status"], "verified"
            )
            self.assertTrue(rows_by_id[record_id]["verified_reference_id"])
            self.assertEqual(
                json.loads(manifest_path.read_text(encoding="utf-8")), manifest
            )
            self.assertNotIn(
                str(Path.home()), manifest_path.read_text(encoding="utf-8")
            )

    def test_candidate_only_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            approval = root / "approval.json"
            self._write_approval(approval)
            candidate_database = root / "candidate-only.db"
            shutil.copy2(CANONICAL_DB, candidate_database)
            with closing(sqlite3.connect(candidate_database)) as connection, connection:
                connection.execute(
                    "UPDATE constant_records SET verification_status = 'candidate'"
                )
                connection.execute(
                    "UPDATE source_references SET verification_status = 'candidate'"
                )
            with self.assertRaisesRegex(ValueError, "No verified records"):
                publish_dataset(
                    candidate_database,
                    approval,
                    root / "dataset.csv",
                    root / "dataset.manifest.json",
                )

    def test_weakened_approval_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            curated, _ = self._build_curated_database(root)
            approval = root / "approval.json"
            self._write_approval(approval)
            data = json.loads(approval.read_text(encoding="utf-8"))
            data["allowed_statuses"] = ["reviewed", "verified"]
            approval.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "allowed_statuses"):
                publish_dataset(
                    curated,
                    approval,
                    root / "dataset.csv",
                    root / "dataset.manifest.json",
                )


if __name__ == "__main__":
    unittest.main()
