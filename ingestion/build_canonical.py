#!/usr/bin/env python3
"""Build an independent canonical candidate database from the NIST staging DB."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from complexation_explorer.io_utils import require_distinct_paths
from ingestion.adapters.nist_srd46 import NistSrd46Adapter, sha256_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = PROJECT_ROOT / "ingestion/canonical_schema.sql"


def portable_report_path(path: Path) -> str:
    """Return a repository-relative path without exposing a local home directory."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return f"<external>/{path.name}"


def build(staging: Path, output: Path, report_path: Path, force: bool) -> dict:
    staging = staging.resolve()
    output = output.resolve()
    report_path = report_path.resolve()
    require_distinct_paths(staging=staging, output=output, report=report_path)
    if not staging.is_file():
        raise FileNotFoundError(f"Staging database not found: {staging}")
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
        adapter_report = NistSrd46Adapter().load(staging, temporary_path)
        with closing(sqlite3.connect(temporary_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            candidate_count = connection.execute(
                "SELECT COUNT(*) FROM constant_records WHERE verification_status = 'candidate'"
            ).fetchone()[0]
            verified_count = connection.execute(
                "SELECT COUNT(*) FROM verified_constant_records"
            ).fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"Canonical database failed integrity check: {integrity}")
            if foreign_key_errors:
                raise ValueError(
                    "Canonical database failed foreign-key validation: "
                    f"{len(foreign_key_errors)} error(s)"
                )
            if candidate_count == 0:
                raise ValueError("Canonical database contains no candidate records")
            connection.execute("ANALYZE")
            connection.execute("VACUUM")

        temporary_path.replace(output)
        report = {
            **adapter_report,
            "input": {
                "path": portable_report_path(staging),
                "sha256": sha256_file(staging),
            },
            "output": {
                "path": portable_report_path(output),
                "sha256": sha256_file(output),
                "size_bytes": output.stat().st_size,
            },
            "validation": {
                "sqlite_integrity": integrity,
                "foreign_key_errors": len(foreign_key_errors),
                "candidate_records": candidate_count,
                "verified_records": verified_count,
                "local_excel_accessed": False,
            },
        }
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return report
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build(args.staging, args.output, args.report, args.force)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Built: {report['output']['path']}")
    print(f"SHA-256: {report['output']['sha256']}")
    print(f"Canonical records: {report['counts']['constant_records']:,}")
    print(f"Verified records: {report['validation']['verified_records']:,}")
    print(f"SQLite integrity: {report['validation']['sqlite_integrity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
