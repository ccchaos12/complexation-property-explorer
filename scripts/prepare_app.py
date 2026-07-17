#!/usr/bin/env python3
"""Prepare the local source and canonical databases for the research app."""

from __future__ import annotations

import os
from pathlib import Path

from ingestion.build_canonical import build as build_canonical
from scripts.build_srd46_sqlite import build_database
from scripts.download_srd46 import ensure_srd46_files


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ARCHIVE = PROJECT_ROOT / "data/raw/SRD 46 SQL.zip"
RAW_README = PROJECT_ROOT / "data/raw/NIST_SRD_46_README.txt"
STAGING_DATABASE = PROJECT_ROOT / "data/generated/NIST_SRD_46_rebuilt.db"
CANONICAL_DATABASE = PROJECT_ROOT / "data/generated/stability_constants_canonical.db"
STAGING_REPORT = PROJECT_ROOT / "data/reports/srd46_build_report.json"
CANONICAL_REPORT = PROJECT_ROOT / "data/reports/canonical_build_report.json"


def prepare() -> Path:
    configured_database = os.environ.get("COMPLEXATION_DB_PATH")
    if configured_database:
        database_path = Path(configured_database).expanduser().resolve()
        if not database_path.is_file():
            raise FileNotFoundError(
                f"COMPLEXATION_DB_PATH does not point to a database: {database_path}"
            )
        print(f"Using the configured database: {database_path}")
        return database_path

    ensure_srd46_files(RAW_ARCHIVE, RAW_README)

    if STAGING_DATABASE.is_file():
        print("The rebuilt NIST SQLite database already exists.")
    else:
        print("Converting the NIST SQL package to SQLite...")
        build_database(RAW_ARCHIVE, STAGING_DATABASE, STAGING_REPORT, force=False)

    if CANONICAL_DATABASE.is_file():
        print("The canonical read-only database already exists.")
    else:
        print("Building the canonical read-only database...")
        build_canonical(
            STAGING_DATABASE,
            CANONICAL_DATABASE,
            CANONICAL_REPORT,
            force=False,
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
