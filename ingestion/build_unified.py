#!/usr/bin/env python3
"""Build the unified NIST and verified local-supplement application database."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from complexation_explorer.io_utils import require_distinct_paths
from ingestion.adapters.local_excel_supplement import LocalExcelSupplementAdapter
from ingestion.adapters.nist_srd46 import NistSrd46Adapter, sha256_file
from ingestion.build_canonical import DEFAULT_SCHEMA, portable_report_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "2.0.0"


def build(
    nist_staging: Path,
    supplement_staging: Path,
    output: Path,
    report_path: Path,
    force: bool,
) -> dict:
    nist_staging = nist_staging.resolve()
    supplement_staging = supplement_staging.resolve()
    output = output.resolve()
    report_path = report_path.resolve()
    require_distinct_paths(
        nist_staging=nist_staging,
        supplement_staging=supplement_staging,
        output=output,
        report=report_path,
    )
    for label, path in (
        ("NIST staging database", nist_staging),
        ("Supplement staging database", supplement_staging),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
    if output.exists() and not force:
        raise FileExistsError(f"Output already exists: {output}; pass --force to rebuild")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=output.stem + ".", suffix=".tmp.db", dir=output.parent, delete=False
    ) as handle:
        temporary_path = Path(handle.name)

    try:
        schema_sql = DEFAULT_SCHEMA.read_text(encoding="utf-8")
        with closing(sqlite3.connect(temporary_path)) as connection, connection:
            connection.executescript(schema_sql)

        nist_report = NistSrd46Adapter().load(nist_staging, temporary_path)
        supplement_report = LocalExcelSupplementAdapter().load(
            supplement_staging, temporary_path
        )

        built_at = datetime.now(UTC).isoformat()
        with closing(sqlite3.connect(temporary_path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")

            connection.execute(
                "UPDATE constant_records SET verification_status = 'verified'"
            )
            connection.execute(
                "UPDATE source_references SET verification_status = 'verified'"
            )
            connection.execute("UPDATE ligands SET identity_status = 'verified'")

            connection.execute("DELETE FROM dataset_release_records")
            connection.execute("DELETE FROM dataset_releases")

            ligand_identity_rows = connection.execute(
                """
                SELECT local_ligand.ligand_id AS source_ligand_id,
                       local_ligand.source_record_id AS source_ligand_record_id,
                       nist_ligand.ligand_id AS matched_ligand_id,
                       nist_ligand.source_record_id AS matched_ligand_record_id,
                       local_ligand.structure_raw
                FROM ligands AS local_ligand
                JOIN ligands AS nist_ligand
                  ON nist_ligand.structure_raw = local_ligand.structure_raw
                JOIN source_versions AS local_version
                  ON local_version.source_version_id = local_ligand.source_version_id
                JOIN source_versions AS nist_version
                  ON nist_version.source_version_id = nist_ligand.source_version_id
                WHERE local_version.source_id = 'SUPPLEMENT'
                  AND nist_version.source_id = 'NIST_SRD46'
                  AND local_ligand.structure_raw IS NOT NULL
                  AND local_ligand.structure_raw NOT LIKE '%"N/A"%'
                ORDER BY CAST(local_ligand.source_record_id AS INTEGER),
                         CAST(nist_ligand.source_record_id AS INTEGER)
                """
            ).fetchall()
            for row in ligand_identity_rows:
                evidence = {
                    "match_method": "exact_mol_data_encoding",
                    "structure_sha256": hashlib.sha256(
                        row["structure_raw"].encode("utf-8")
                    ).hexdigest(),
                }
                connection.execute(
                    """
                    INSERT INTO ligand_identity_relationships (
                        identity_relationship_id, source_ligand_id,
                        matched_ligand_id, relationship_type,
                        evidence_json, created_at_utc
                    ) VALUES (?, ?, ?, 'exact_structure', ?, ?)
                    """,
                    (
                        "SUPPLEMENT:LIGAND_IDENTITY:"
                        f"{row['source_ligand_record_id']}:"
                        f"{row['matched_ligand_record_id']}",
                        row["source_ligand_id"],
                        row["matched_ligand_id"],
                        json.dumps(
                            evidence, sort_keys=True, separators=(",", ":")
                        ),
                        built_at,
                    ),
                )

            duplicate_constant_rows = connection.execute(
                """
                SELECT local_constant.record_id AS duplicate_record_id,
                       local_constant.source_record_id AS duplicate_source_record_id,
                       nist_constant.record_id AS preferred_record_id,
                       nist_constant.source_record_id AS preferred_source_record_id
                FROM constant_records AS local_constant
                JOIN ligands AS local_ligand
                  ON local_ligand.ligand_id = local_constant.ligand_id
                JOIN ligands AS nist_ligand
                  ON nist_ligand.structure_raw = local_ligand.structure_raw
                JOIN source_versions AS local_version
                  ON local_version.source_version_id = local_ligand.source_version_id
                JOIN source_versions AS nist_version
                  ON nist_version.source_version_id = nist_ligand.source_version_id
                JOIN constant_records AS nist_constant
                  ON nist_constant.ligand_id = nist_ligand.ligand_id
                 AND nist_constant.metal_species_id
                   = local_constant.metal_species_id
                 AND nist_constant.value_type = local_constant.value_type
                 AND COALESCE(nist_constant.equilibrium_raw, '')
                   = COALESCE(local_constant.equilibrium_raw, '')
                 AND COALESCE(nist_constant.reported_value_text, '')
                   = COALESCE(local_constant.reported_value_text, '')
                 AND COALESCE(nist_constant.temperature_raw, '')
                   = COALESCE(local_constant.temperature_raw, '')
                 AND COALESCE(nist_constant.ionic_strength_raw, '')
                   = COALESCE(local_constant.ionic_strength_raw, '')
                WHERE local_version.source_id = 'SUPPLEMENT'
                  AND nist_version.source_id = 'NIST_SRD46'
                  AND local_ligand.structure_raw IS NOT NULL
                  AND local_ligand.structure_raw NOT LIKE '%"N/A"%'
                ORDER BY CAST(local_constant.source_record_id AS INTEGER),
                         CAST(nist_constant.source_record_id AS INTEGER)
                """
            ).fetchall()
            duplicate_match_fields = [
                "ligand_structure",
                "metal_species_id",
                "value_type",
                "equilibrium_raw",
                "reported_value_text",
                "temperature_raw",
                "ionic_strength_raw",
            ]
            for row in duplicate_constant_rows:
                evidence = {
                    "match_method": "strict_exact_cross_source",
                    "matched_fields": duplicate_match_fields,
                    "preferred_source": "NIST_SRD46",
                    "duplicate_source": "SUPPLEMENT",
                }
                connection.execute(
                    """
                    INSERT INTO constant_record_relationships (
                        relationship_id, duplicate_record_id,
                        preferred_record_id, relationship_type,
                        evidence_json, created_at_utc
                    ) VALUES (
                        ?, ?, ?, 'strict_cross_source_duplicate', ?, ?
                    )
                    """,
                    (
                        "SUPPLEMENT:CONSTANT_DUPLICATE:"
                        f"{row['duplicate_source_record_id']}:"
                        f"{row['preferred_source_record_id']}",
                        row["duplicate_record_id"],
                        row["preferred_record_id"],
                        json.dumps(
                            evidence, sort_keys=True, separators=(",", ":")
                        ),
                        built_at,
                    ),
                )

            source_fingerprint = hashlib.sha256(
                (
                    sha256_file(nist_staging)
                    + sha256_file(supplement_staging)
                ).encode("ascii")
            ).hexdigest()
            release_id = f"UNIFIED-VERIFIED-{source_fingerprint[:12]}"
            record_count = connection.execute(
                "SELECT COUNT(*) FROM active_constant_records"
            ).fetchone()[0]
            deduplicated_record_count = connection.execute(
                "SELECT COUNT(*) FROM deduplicated_active_constant_records"
            ).fetchone()[0]
            manifest = {
                "source_version_ids": [
                    row[0]
                    for row in connection.execute(
                        "SELECT source_version_id FROM source_versions ORDER BY source_version_id"
                    )
                ],
                "record_count": record_count,
                "deduplicated_record_count": deduplicated_record_count,
                "exact_structure_ligand_relationships": len(
                    ligand_identity_rows
                ),
                "strict_cross_source_duplicate_relationships": len(
                    duplicate_constant_rows
                ),
                "verification_status": "verified",
                "verification_basis": "project_owner_declared_all_verified",
                "record_level_review_events_created": False,
                "training_approved": False,
            }
            connection.execute(
                """
                INSERT INTO dataset_releases (
                    release_id, release_name, release_status, intended_use,
                    schema_version, created_at_utc, record_count, manifest_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    release_id,
                    "Unified NIST SRD 46 and local supplement verified release",
                    "reviewed",
                    "local_application_exploration",
                    SCHEMA_VERSION,
                    built_at,
                    record_count,
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                ),
            )
            connection.execute(
                """
                INSERT INTO dataset_release_records (release_id, record_id)
                SELECT ?, record_id FROM active_constant_records
                """,
                (release_id,),
            )

            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_errors = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            verified_count = connection.execute(
                "SELECT COUNT(*) FROM verified_constant_records"
            ).fetchone()[0]
            exact_reference_count = connection.execute(
                """
                SELECT COUNT(*) FROM constant_records
                WHERE source_version_id = ?
                  AND verified_reference_id IS NOT NULL
                """,
                (supplement_report["source_version_id"],),
            ).fetchone()[0]
            exact_structure_match_ligands = len(
                {row["source_ligand_id"] for row in ligand_identity_rows}
            )
            formula_match_ligands = connection.execute(
                """
                SELECT COUNT(DISTINCT local_ligand.ligand_id)
                FROM ligands AS local_ligand
                JOIN ligands AS nist_ligand
                  ON LOWER(TRIM(nist_ligand.formula_raw))
                   = LOWER(TRIM(local_ligand.formula_raw))
                JOIN source_versions AS local_version
                  ON local_version.source_version_id = local_ligand.source_version_id
                JOIN source_versions AS nist_version
                  ON nist_version.source_version_id = nist_ligand.source_version_id
                WHERE local_version.source_id = 'SUPPLEMENT'
                  AND nist_version.source_id = 'NIST_SRD46'
                  AND TRIM(local_ligand.formula_raw) <> ''
                  AND local_ligand.formula_raw <> 'N/A'
                """
            ).fetchone()[0]
            strict_cross_source_duplicate_constants = len(
                duplicate_constant_rows
            )
            if integrity != "ok":
                raise ValueError(
                    f"Unified canonical database failed integrity check: {integrity}"
                )
            if foreign_key_errors:
                raise ValueError(
                    "Unified canonical database failed foreign-key validation: "
                    f"{len(foreign_key_errors)} error(s)"
                )
            if verified_count != record_count:
                raise ValueError(
                    "All-verified policy failed: "
                    f"{verified_count} verified of {record_count} active records"
                )
            if exact_reference_count != supplement_report["counts"]["constant_records"]:
                raise ValueError(
                    "Supplement exact-reference validation failed: "
                    f"{exact_reference_count} linked records"
                )
            if record_count - deduplicated_record_count != len(
                duplicate_constant_rows
            ):
                raise ValueError(
                    "Duplicate relationship validation failed: "
                    f"{record_count - deduplicated_record_count} hidden records "
                    f"for {len(duplicate_constant_rows)} relationships"
                )
            connection.commit()
            connection.execute("ANALYZE")
            connection.commit()
            connection.execute("VACUUM")

        temporary_path.replace(output)
        report = {
            "builder": "unified_canonical",
            "schema_version": SCHEMA_VERSION,
            "verification_basis": "project_owner_declared_all_verified",
            "inputs": {
                "nist": {
                    "path": portable_report_path(nist_staging),
                    "sha256": sha256_file(nist_staging),
                },
                "supplement": {
                    "path": portable_report_path(supplement_staging),
                    "sha256": sha256_file(supplement_staging),
                },
            },
            "adapters": {
                "nist": nist_report,
                "supplement": supplement_report,
            },
            "output": {
                "path": portable_report_path(output),
                "sha256": sha256_file(output),
                "size_bytes": output.stat().st_size,
            },
            "validation": {
                "sqlite_integrity": integrity,
                "foreign_key_errors": len(foreign_key_errors),
                "active_records": record_count,
                "deduplicated_active_records": deduplicated_record_count,
                "verified_records": verified_count,
                "supplement_exact_reference_records": exact_reference_count,
                "review_events": 0,
                "training_approved": False,
            },
            "duplicate_screening": {
                "supplement_ligands_with_exact_nist_structure": (
                    exact_structure_match_ligands
                ),
                "supplement_ligands_sharing_formula_with_nist": (
                    formula_match_ligands
                ),
                "strict_cross_source_duplicate_constants": (
                    strict_cross_source_duplicate_constants
                ),
                "ligand_identity_relationships": len(ligand_identity_rows),
                "constant_duplicate_relationships": len(
                    duplicate_constant_rows
                ),
                "action": (
                    "classified_and_retained; duplicate side hidden from "
                    "default search"
                ),
            },
        }
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return report
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nist-staging", required=True, type=Path)
    parser.add_argument("--supplement-staging", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build(
            args.nist_staging,
            args.supplement_staging,
            args.output,
            args.report,
            args.force,
        )
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Built: {report['output']['path']}")
    print(f"SHA-256: {report['output']['sha256']}")
    print(f"Active records: {report['validation']['active_records']:,}")
    print(f"Verified records: {report['validation']['verified_records']:,}")
    print(f"SQLite integrity: {report['validation']['sqlite_integrity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
