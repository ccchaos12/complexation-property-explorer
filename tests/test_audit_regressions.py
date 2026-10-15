"""Portable regressions for scientific identity, provenance, and deduplication."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from complexation_explorer.database import (
    SearchFilters,
    count_constants,
    get_database_summary,
    get_record_detail,
    search_constants,
)
from ingestion.adapters.nist_srd46 import strict_float
from ingestion.build_unified import build
from publication.publish_dataset import PUBLISH_QUERY
from scripts.prepare_app import validate_canonical_database
from tests.support import create_test_database

PREFERRED = "NIST_SRD46:CONSTANT:100001"
SECOND = "NIST_SRD46:CONSTANT:100002"
DUPLICATE = "LOCAL_XLSX:CONSTANT:100001"
REFERENCE = "NIST_SRD46:REFERENCE:1"
MATCH_FIELDS = (
    "metal_species_id",
    "value_type",
    "equilibrium_raw",
    "reported_value_text",
    "numeric_value",
    "temperature_raw",
    "temperature_c",
    "temperature_k",
    "ionic_strength_raw",
    "ionic_strength_numeric",
    "solvent_raw",
    "electrolyte_raw",
)


class ScientificIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = create_test_database(self.root / "fixture.db")
        self.output = self.root / "unified.db"
        with closing(sqlite3.connect(self.fixture)) as connection, connection:
            connection.execute(
                "UPDATE sources SET source_id = 'SUPPLEMENT' WHERE source_id = 'LOCAL_XLSX'"
            )
            connection.execute(
                "UPDATE source_versions SET source_id = 'SUPPLEMENT' WHERE source_id = 'LOCAL_XLSX'"
            )
            connection.execute("UPDATE ligands SET structure_raw = ?", ('["encoded-molecule"]',))
            assignments = ", ".join(
                f"{field} = (SELECT {field} FROM constant_records WHERE record_id = ?)"
                for field in MATCH_FIELDS
            )
            connection.execute(
                f"UPDATE constant_records SET {assignments} WHERE record_id = ?",
                (*([PREFERRED] * len(MATCH_FIELDS)), DUPLICATE),
            )
            connection.execute(
                "UPDATE constant_records SET verified_reference_id = ? WHERE record_id = ?",
                (REFERENCE, DUPLICATE),
            )

    def build_fixture(self):
        # Mock only the source adapters; exercise the production relationship SQL,
        # validation, release manifest and atomic output installation end to end.
        def load_nist(_staging, target):
            with (
                closing(sqlite3.connect(self.fixture)) as source,
                closing(sqlite3.connect(target)) as dest,
            ):
                source.backup(dest)
            return {"source_version_id": "NIST_SRD46:TEST"}

        with (
            patch("ingestion.build_unified.NistSrd46Adapter.load", side_effect=load_nist),
            patch(
                "ingestion.build_unified.LocalExcelSupplementAdapter.load",
                return_value={
                    "source_version_id": "LOCAL_XLSX:TEST",
                    "counts": {"constant_records": 1},
                },
            ),
        ):
            return build(
                self.fixture,
                self.root / "supplement.db",
                self.output,
                self.root / "report.json",
                force=True,
            )

    def run_build(self):
        (self.root / "supplement.db").write_bytes(b"fixture input fingerprint")
        return self.build_fixture()

    def test_matching_records_retain_both_sources_but_hide_one(self):
        report = self.run_build()
        self.assertEqual(report["validation"]["active_records"], 3)
        self.assertEqual(report["validation"]["deduplicated_active_records"], 2)
        self.assertEqual(count_constants(SearchFilters(), self.output), 2)
        self.assertEqual(
            count_constants(SearchFilters(include_strict_duplicates=True), self.output), 3
        )
        with closing(sqlite3.connect(self.output)) as connection:
            evidence = json.loads(
                connection.execute(
                    "SELECT evidence_json FROM constant_record_relationships"
                ).fetchone()[0]
            )
        self.assertIn("solvent_raw", evidence["matched_fields"])
        self.assertIn("electrolyte_raw", evidence["matched_fields"])

    def test_different_or_missing_medium_never_hides_a_record(self):
        for field, value in [
            ("solvent_raw", "DMSO"),
            ("solvent_raw", None),
            ("electrolyte_raw", "KNO3"),
        ]:
            with self.subTest(field=field, value=value):
                with closing(sqlite3.connect(self.fixture)) as connection, connection:
                    connection.execute(
                        "UPDATE constant_records SET solvent_raw = 'H<sub>2</sub>O', electrolyte_raw = NULL"
                    )
                    connection.execute(
                        f"UPDATE constant_records SET {field} = ? WHERE record_id = ?",
                        (value, DUPLICATE),
                    )
                report = self.run_build()
                self.assertEqual(report["validation"]["deduplicated_active_records"], 3)
                self.assertEqual(count_constants(SearchFilters(), self.output), 3)

    def test_missing_structures_do_not_establish_identity(self):
        for raw in (
            None,
            "[]",
            "[null]",
            '[""]',
            '["N/A"]',
            '[" n/a "]',
            '["***"]',
            "{}",
            "not json",
        ):
            with self.subTest(raw=raw):
                with closing(sqlite3.connect(self.fixture)) as connection, connection:
                    connection.execute("UPDATE ligands SET structure_raw = ?", (raw,))
                report = self.run_build()
                self.assertEqual(report["duplicate_screening"]["ligand_identity_relationships"], 0)
                self.assertEqual(report["validation"]["deduplicated_active_records"], 3)

    def test_multiple_preferred_matches_count_one_hidden_record(self):
        with closing(sqlite3.connect(self.fixture)) as connection, connection:
            assignments = ", ".join(
                f"{field} = (SELECT {field} FROM constant_records WHERE record_id = ?)"
                for field in MATCH_FIELDS
            )
            connection.execute(
                f"UPDATE constant_records SET {assignments} WHERE record_id = ?",
                (*([PREFERRED] * len(MATCH_FIELDS)), SECOND),
            )
        report = self.run_build()
        self.assertEqual(report["duplicate_screening"]["constant_duplicate_relationships"], 2)
        self.assertEqual(
            report["duplicate_screening"]["strict_cross_source_duplicate_constants"], 1
        )
        self.assertEqual(get_database_summary(self.output)["strict_duplicate_records"], 1)
        validate_canonical_database(
            self.output, expected_staging_sha256="b" * 64, expected_supplement_sha256="d" * 64
        )

    def test_inactive_preferred_record_restores_active_duplicate(self):
        self.run_build()
        with closing(sqlite3.connect(self.output)) as connection, connection:
            connection.execute(
                "UPDATE constant_records SET verification_status = 'rejected', is_active = 0 WHERE record_id = ?",
                (PREFERRED,),
            )
        visible = search_constants(SearchFilters(), self.output)
        self.assertIn(DUPLICATE, {row["record_id"] for row in visible})
        self.assertEqual(count_constants(SearchFilters(), self.output), 2)
        summary = get_database_summary(self.output)
        self.assertEqual(summary["deduplicated_constants"], 2)
        self.assertEqual(summary["strict_duplicate_records"], 0)

    def test_publication_keeps_duplicate_when_preferred_is_ineligible(self):
        self.run_build()
        with closing(sqlite3.connect(self.output)) as connection, connection:
            # NIST is verified for app use but has no exact reference. The local
            # record has an exact reference and must survive publication filtering.
            rows = connection.execute(PUBLISH_QUERY).fetchall()
            self.assertEqual([row[0] for row in rows], [DUPLICATE])
            connection.execute(
                "UPDATE constant_records SET verified_reference_id = ? WHERE record_id = ?",
                (REFERENCE, PREFERRED),
            )
            self.assertEqual([row[0] for row in connection.execute(PUBLISH_QUERY)], [PREFERRED])
            connection.execute(
                "UPDATE constant_records SET verification_status = 'rejected', is_active = 0 WHERE record_id = ?",
                (PREFERRED,),
            )
            self.assertEqual([row[0] for row in connection.execute(PUBLISH_QUERY)], [DUPLICATE])

    def test_exact_reference_survives_queries_without_pair_candidate_links(self):
        self.run_build()
        detail = get_record_detail(DUPLICATE, self.output)
        self.assertEqual(detail["verified_reference"], "Fixture reference")
        row = next(
            row
            for row in search_constants(SearchFilters(include_strict_duplicates=True), self.output)
            if row["record_id"] == DUPLICATE
        )
        self.assertEqual(row["candidate_reference_count"], 0)
        self.assertEqual(row["verified_reference_id"], REFERENCE)
        self.assertEqual(row["verified_reference"], "Fixture reference")

    def test_previous_schema_is_rejected_with_rebuild_instructions(self):
        with closing(sqlite3.connect(self.fixture)) as connection:
            connection.execute("PRAGMA user_version = 2")
        for reader in (get_database_summary, validate_canonical_database):
            with (
                self.subTest(reader=reader.__name__),
                self.assertRaisesRegex(ValueError, "Rebuild generated databases"),
            ):
                reader(self.fixture)

    def test_exact_reference_is_visible_and_exported_in_app(self):
        from streamlit.testing.v1 import AppTest

        self.run_build()
        with patch.dict(os.environ, {"COMPLEXATION_DB_PATH": str(self.output)}):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
                timeout=30
            )
            app.checkbox(key="explorer_include_strict_duplicates").check().run()
            app.text_input(key="explorer_ligand_text").set_value("Glycine").run()
            self.assertEqual(list(app.exception), [])
            self.assertTrue(
                any("Directly linked to this record" in item.value for item in app.markdown)
            )
            self.assertTrue(any("Fixture reference" in item.value for item in app.markdown))
            next(
                button for button in app.button if button.label == "Prepare filtered CSV"
            ).click().run()
            csv = app.session_state["_explorer_export_csv"].decode("utf-8-sig")
            self.assertIn("Verified reference ID", csv)
            self.assertIn(REFERENCE, csv)
            self.assertIn("Fixture reference", csv)


class StrictNumericTests(unittest.TestCase):
    def test_float_overflow_cannot_become_an_infinite_constant(self):
        for text in ("1e999", "-1e999", "NaN", "inf", "(7.2)"):
            with self.subTest(text=text):
                self.assertIsNone(strict_float(text))
        self.assertEqual(strict_float("0"), 0.0)
        self.assertEqual(strict_float("-1.2e2"), -120.0)


class SchemaUpgradeTests(unittest.TestCase):
    def test_launcher_preserves_old_default_database_before_rebuilding(self):
        from scripts import prepare_app
        from scripts.download_srd46 import sha256_file

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = create_test_database(root / "app.db")
            with closing(sqlite3.connect(old)) as connection:
                connection.execute("PRAGMA user_version = 2")
            original_bytes = old.read_bytes()
            staging = root / "staging.db"
            staging.write_bytes(b"validated staging fixture")

            def rebuild(_staging, output, _report, force):
                create_test_database(output)
                with closing(sqlite3.connect(output)) as connection, connection:
                    connection.execute(
                        "UPDATE source_versions SET staging_checksum_sha256 = ? WHERE source_id = 'NIST_SRD46'",
                        (sha256_file(staging),),
                    )

            with (
                patch.dict(os.environ, {"COMPLEXATION_DB_PATH": ""}),
                patch.multiple(
                    prepare_app,
                    CANONICAL_DATABASE=old,
                    STAGING_DATABASE=staging,
                    SUPPLEMENT_DATABASE=root / "absent.db",
                ),
                patch.object(prepare_app, "ensure_srd46_files"),
                patch.object(prepare_app, "validate_staging_database"),
                patch.object(prepare_app, "build_canonical", side_effect=rebuild) as builder,
            ):
                self.assertEqual(prepare_app.prepare(), old)
            builder.assert_called_once()
            backups = list(root.glob("app.invalid-*.db"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original_bytes)
            validate_canonical_database(old)

    def test_custom_old_database_is_rejected_without_modification(self):
        from scripts.prepare_app import prepare

        with tempfile.TemporaryDirectory() as directory:
            old = create_test_database(Path(directory) / "custom.db")
            with closing(sqlite3.connect(old)) as connection:
                connection.execute("PRAGMA user_version = 2")
            original_bytes = old.read_bytes()
            with patch.dict(os.environ, {"COMPLEXATION_DB_PATH": str(old)}):
                with self.assertRaisesRegex(ValueError, "reapply the saved review decisions"):
                    prepare()
            self.assertEqual(old.read_bytes(), original_bytes)
