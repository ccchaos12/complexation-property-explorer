#!/usr/bin/env python3
"""Prepare the local source and canonical databases for the research app."""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_ROOT))

from complexation_explorer.io_utils import readonly_sqlite_uri  # noqa: E402
from ingestion.build_canonical import build as build_canonical  # noqa: E402
from scripts.build_srd46_sqlite import build_database  # noqa: E402
from scripts.download_srd46 import (  # noqa: E402
    NIST_SRD46_SQL_SHA256,
    ensure_srd46_files,
    sha256_file,
)

RAW_ARCHIVE = PROJECT_ROOT / "data/raw/SRD 46 SQL.zip"
RAW_README = PROJECT_ROOT / "data/raw/NIST_SRD_46_README.txt"
STAGING_DATABASE = PROJECT_ROOT / "data/generated/NIST_SRD_46_rebuilt.db"
CANONICAL_DATABASE = PROJECT_ROOT / "data/generated/stability_constants_canonical.db"
STAGING_REPORT = PROJECT_ROOT / "data/reports/srd46_build_report.json"
CANONICAL_REPORT = PROJECT_ROOT / "data/reports/canonical_build_report.json"


def _preserve_invalid_database(path: Path) -> Path:
    suffix = time.strftime("%Y%m%d-%H%M%S")
    base_name = f"{path.stem}.invalid-{suffix}"
    preserved = path.with_name(f"{base_name}{path.suffix}")
    counter = 1
    while preserved.exists():
        preserved = path.with_name(f"{base_name}-{counter}{path.suffix}")
        counter += 1
    path.replace(preserved)
    return preserved


def _validate_sqlite_objects(path: Path, required_objects: set[str]) -> sqlite3.Connection:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Database is missing or empty: {path}")

    connection = sqlite3.connect(readonly_sqlite_uri(path), uri=True, timeout=10)
    try:
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite quick check failed: {integrity}")
        objects = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        missing = required_objects - objects
        if missing:
            raise ValueError(
                "Database is incompatible; missing: " + ", ".join(sorted(missing))
            )
        return connection
    except Exception:
        connection.close()
        raise


def validate_staging_database(path: Path) -> None:
    """Validate the generated NIST staging database before reusing it."""
    required = {
        "_build_metadata",
        "beta_definition",
        "constanttyp",
        "footnote",
        "ligand_class",
        "liganden",
        "literature_alt",
        "metal",
        "mol_data",
        "solvent",
        "verkn_ligand_metal",
        "verkn_ligand_metal_literature",
    }
    try:
        with closing(_validate_sqlite_objects(path, required)) as connection:
            metadata = dict(connection.execute("SELECT key, value FROM _build_metadata"))
            if metadata.get("source_sha256") != NIST_SRD46_SQL_SHA256:
                raise ValueError("Staging database source checksum is not the pinned NIST archive")
            if connection.execute("SELECT COUNT(*) FROM verkn_ligand_metal").fetchone()[0] == 0:
                raise ValueError("Staging database contains no constant records")
    except sqlite3.DatabaseError as error:
        raise ValueError(f"Staging database cannot be read: {error}") from error


def validate_canonical_database(
    path: Path,
    *,
    expected_staging_sha256: str | None = None,
) -> None:
    """Validate canonical schema, relationships, and optional staging provenance."""
    required = {
        "dataset_releases",
        "ligand_metal_reference_candidates",
        "sources",
        "source_versions",
        "source_references",
        "metal_species",
        "ligands",
        "constant_records",
        "active_constant_records",
    }
    try:
        with closing(_validate_sqlite_objects(path, required)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Canonical database failed foreign-key validation")
            schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if schema_version != 1:
                raise ValueError(
                    f"Unsupported canonical schema version: {schema_version}; expected 1"
                )
            if connection.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0] == 0:
                raise ValueError("Canonical database has no source version metadata")
            connection.execute(
                """
                SELECT v.record_id, v.value_type, v.reported_value_text,
                       l.ligand_name_raw, m.display_name_raw,
                       s.source_id, sv.version_label
                FROM active_constant_records AS v
                JOIN ligands AS l ON l.ligand_id = v.ligand_id
                JOIN metal_species AS m ON m.metal_species_id = v.metal_species_id
                JOIN source_versions AS sv
                  ON sv.source_version_id = v.source_version_id
                JOIN sources AS s ON s.source_id = sv.source_id
                LIMIT 1
                """
            ).fetchone()
            if expected_staging_sha256 is not None:
                matching_versions = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM source_versions
                    WHERE source_id = 'NIST_SRD46'
                      AND staging_checksum_sha256 = ?
                    """,
                    (expected_staging_sha256,),
                ).fetchone()[0]
                if matching_versions == 0:
                    raise ValueError(
                        "Canonical database does not match the current NIST staging database"
                    )
    except sqlite3.DatabaseError as error:
        raise ValueError(f"Canonical database cannot be read: {error}") from error


def prepare() -> Path:
    configured_database = os.environ.get("COMPLEXATION_DB_PATH")
    if configured_database:
        database_path = Path(configured_database).expanduser().resolve()
        if not database_path.is_file():
            raise FileNotFoundError(
                f"COMPLEXATION_DB_PATH does not point to a database: {database_path}"
            )
        validate_canonical_database(database_path)
        print(f"Using the configured database: {database_path}")
        return database_path

    ensure_srd46_files(RAW_ARCHIVE, RAW_README)

    if STAGING_DATABASE.is_file():
        try:
            validate_staging_database(STAGING_DATABASE)
            print("The rebuilt NIST SQLite database is present and valid.")
        except ValueError as error:
            preserved = _preserve_invalid_database(STAGING_DATABASE)
            print(f"Preserved an invalid staging database as: {preserved.name}")
            print(f"Rebuild reason: {error}")

    if not STAGING_DATABASE.is_file():
        print("Converting the NIST SQL package to SQLite...")
        build_database(RAW_ARCHIVE, STAGING_DATABASE, STAGING_REPORT, force=False)
        validate_staging_database(STAGING_DATABASE)

    staging_sha256 = sha256_file(STAGING_DATABASE)
    if CANONICAL_DATABASE.is_file():
        try:
            validate_canonical_database(
                CANONICAL_DATABASE,
                expected_staging_sha256=staging_sha256,
            )
            print("The canonical read-only database is present and valid.")
        except ValueError as error:
            preserved = _preserve_invalid_database(CANONICAL_DATABASE)
            print(f"Preserved an invalid canonical database as: {preserved.name}")
            print(f"Rebuild reason: {error}")

    if not CANONICAL_DATABASE.is_file():
        print("Building the canonical read-only database...")
        build_canonical(
            STAGING_DATABASE,
            CANONICAL_DATABASE,
            CANONICAL_REPORT,
            force=False,
        )
        validate_canonical_database(
            CANONICAL_DATABASE,
            expected_staging_sha256=staging_sha256,
        )

    return CANONICAL_DATABASE


def main() -> int:
    try:
        database_path = prepare()
    except Exception as error:
        print(f"ERROR: {error}")
        return 1
    print(f"Application database ready: {database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
