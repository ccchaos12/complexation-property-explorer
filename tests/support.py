from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "ingestion" / "canonical_schema.sql"


def create_test_database(path: Path) -> Path:
    """Create a tiny two-source database for portable query and UI tests."""
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.executemany(
            """
            INSERT INTO sources (
                source_id, source_name, source_type, publisher, doi,
                license_url, source_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "NIST_SRD46",
                    "NIST SRD 46",
                    "database",
                    "NIST",
                    "10.18434/M32154",
                    "https://www.nist.gov/open/license",
                    "Test fixture",
                ),
                (
                    "LOCAL_XLSX",
                    "Reviewed local workbook",
                    "spreadsheet",
                    None,
                    None,
                    None,
                    "Test fixture",
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO source_versions (
                source_version_id, source_id, version_label,
                source_checksum_sha256, staging_checksum_sha256,
                ingested_at_utc, adapter_name, adapter_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "NIST_SRD46:TEST",
                    "NIST_SRD46",
                    "SRD 46 test fixture",
                    "a" * 64,
                    "b" * 64,
                    "2026-07-16T00:00:00+00:00",
                    "NistSrd46Adapter",
                    "test",
                ),
                (
                    "LOCAL_XLSX:TEST",
                    "LOCAL_XLSX",
                    "Local test fixture",
                    "c" * 64,
                    "d" * 64,
                    "2026-07-16T01:00:00+00:00",
                    "ExcelAdapter",
                    "test",
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO metal_species (
                metal_species_id, source_version_id, source_record_id,
                display_name_raw, source_code, species_type,
                identity_status, source_comment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "NIST_SRD46:METAL:NI2",
                    "NIST_SRD46:TEST",
                    "NI2",
                    "Ni<sup>2+</sup>",
                    "Ni",
                    1,
                    "source_identity",
                    None,
                ),
                (
                    "LOCAL_XLSX:METAL:CO2",
                    "LOCAL_XLSX:TEST",
                    "CO2",
                    "Co<sup>2+</sup>",
                    "Co",
                    1,
                    "source_identity",
                    None,
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO ligands (
                ligand_id, source_version_id, source_record_id,
                ligand_name_raw, formula_raw, ligand_class_raw,
                structure_raw, identity_status, source_comment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "NIST_SRD46:LIGAND:EDTA",
                    "NIST_SRD46:TEST",
                    "EDTA",
                    "EDTA",
                    "C10H16N2O8",
                    "Aminopolycarboxylate",
                    None,
                    "source_identity",
                    None,
                ),
                (
                    "LOCAL_XLSX:LIGAND:GLY",
                    "LOCAL_XLSX:TEST",
                    "GLY",
                    "Glycine",
                    "C2H5N1O2",
                    "Amino acid",
                    None,
                    "reviewed",
                    None,
                ),
            ],
        )
        connection.execute(
            """
            INSERT INTO source_references (
                reference_id, source_version_id, source_record_id,
                reference_code, citation_raw, verification_status, source_comment
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "NIST_SRD46:REFERENCE:1",
                "NIST_SRD46:TEST",
                "1",
                "R1",
                "Fixture reference",
                "candidate",
                None,
            ),
        )
        records = [
            (
                "NIST_SRD46:CONSTANT:100001",
                "NIST_SRD46:TEST",
                "100001",
                "NIST_SRD46:LIGAND:EDTA",
                "NIST_SRD46:METAL:NI2",
                "[ML]/[M][L]",
                "K",
                "18.5",
                18.5,
                "18.5",
                "25",
                25.0,
                298.15,
                "0.1",
                0.1,
                "H<sub>2</sub>O",
                None,
                "0.1",
                None,
                None,
                "ligand_metal",
                "candidate",
                "[]",
                None,
                None,
                1,
                "2026-07-16T00:00:00+00:00",
            ),
            (
                "NIST_SRD46:CONSTANT:100002",
                "NIST_SRD46:TEST",
                "100002",
                "NIST_SRD46:LIGAND:EDTA",
                "NIST_SRD46:METAL:NI2",
                "[ML<sub>2</sub>]/[M][L]<sup>2</sup>",
                "K",
                "ca. 7",
                None,
                "ca. 7",
                "50",
                50.0,
                323.15,
                "0.5",
                0.5,
                "H<sub>2</sub>O",
                None,
                None,
                None,
                None,
                "ligand_metal",
                "candidate",
                '["reported_value_not_strict_numeric"]',
                None,
                None,
                1,
                "2026-07-16T00:00:00+00:00",
            ),
            (
                "LOCAL_XLSX:CONSTANT:100001",
                "LOCAL_XLSX:TEST",
                "100001",
                "LOCAL_XLSX:LIGAND:GLY",
                "LOCAL_XLSX:METAL:CO2",
                "[ML]/[M][L]",
                "K",
                "4.2",
                4.2,
                "4.2",
                "20",
                20.0,
                293.15,
                "0.2",
                0.2,
                "H<sub>2</sub>O",
                None,
                None,
                None,
                None,
                "record",
                "verified",
                "[]",
                None,
                None,
                1,
                "2026-07-16T01:00:00+00:00",
            ),
        ]
        connection.executemany(
            """
            INSERT INTO constant_records (
                record_id, source_version_id, source_record_id, ligand_id,
                metal_species_id, equilibrium_raw, value_type,
                reported_value_text, numeric_value,
                source_standardized_value_text, temperature_raw,
                temperature_c, temperature_k, ionic_strength_raw,
                ionic_strength_numeric, solvent_raw, electrolyte_raw,
                uncertainty_raw, footnote_raw, source_comment,
                provenance_granularity, verification_status, quality_flags_json,
                verified_reference_id, supersedes_record_id, is_active,
                created_at_utc
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            records,
        )
        connection.execute(
            """
            INSERT INTO ligand_metal_reference_candidates (
                link_id, source_version_id, source_record_id, ligand_id,
                metal_species_id, reference_id, resolution_status,
                not_used_flag, source_comment
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "NIST_SRD46:LINK:1",
                "NIST_SRD46:TEST",
                "1",
                "NIST_SRD46:LIGAND:EDTA",
                "NIST_SRD46:METAL:NI2",
                "NIST_SRD46:REFERENCE:1",
                "resolved",
                0,
                None,
            ),
        )
    return path
