#!/usr/bin/env python3
"""Apply explicit review decisions to a new curated database copy."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from complexation_explorer.io_utils import readonly_sqlite_uri, require_distinct_paths

REQUIRED_COLUMNS = (
    "review_id",
    "record_id",
    "decision",
    "reviewer",
    "reviewed_at_utc",
    "reason",
    "verified_reference_id",
    "supersedes_record_id",
)
DECISIONS = {"reviewed", "verified", "rejected"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def portable_report_path(path: Path) -> str:
    """Return a repository-relative path without exposing a local home directory."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return f"<external>/{path.name}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("reviewed_at_utc must include a UTC offset")
    return parsed.astimezone(UTC).isoformat()


def read_decisions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
            raise ValueError(
                "Decision CSV headers must match the template exactly: "
                + ",".join(REQUIRED_COLUMNS)
            )
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    if not rows:
        raise ValueError("Decision CSV contains no review decisions")

    review_ids = set()
    record_ids = set()
    for line_number, row in enumerate(rows, start=2):
        for field in ("review_id", "record_id", "decision", "reviewer", "reviewed_at_utc", "reason"):
            if not row[field]:
                raise ValueError(f"Line {line_number}: {field} is required")
        if row["decision"] not in DECISIONS:
            raise ValueError(f"Line {line_number}: unsupported decision {row['decision']}")
        if row["review_id"] in review_ids:
            raise ValueError(f"Line {line_number}: duplicate review_id {row['review_id']}")
        if row["record_id"] in record_ids:
            raise ValueError(f"Line {line_number}: duplicate record_id {row['record_id']}")
        review_ids.add(row["review_id"])
        record_ids.add(row["record_id"])
        row["reviewed_at_utc"] = parse_utc(row["reviewed_at_utc"])

        if row["decision"] == "verified" and not row["verified_reference_id"]:
            raise ValueError(
                f"Line {line_number}: verified decisions require verified_reference_id"
            )
        if row["decision"] != "verified" and row["verified_reference_id"]:
            raise ValueError(
                f"Line {line_number}: only verified decisions may set verified_reference_id"
            )
        if row["decision"] != "verified" and row["supersedes_record_id"]:
            raise ValueError(
                f"Line {line_number}: only verified decisions may supersede a record"
            )
        if row["record_id"] == row["supersedes_record_id"]:
            raise ValueError(f"Line {line_number}: a record cannot supersede itself")
    return rows


def apply_reviews(
    canonical_path: Path,
    decisions_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    force: bool = False,
) -> dict:
    canonical_path = canonical_path.resolve()
    decisions_path = decisions_path.resolve()
    output_path = output_path.resolve()
    report_path = report_path.resolve()
    require_distinct_paths(
        canonical=canonical_path,
        decisions=decisions_path,
        output=output_path,
        report=report_path,
    )
    if not canonical_path.is_file():
        raise FileNotFoundError(f"Canonical database not found: {canonical_path}")
    if not decisions_path.is_file():
        raise FileNotFoundError(f"Decision CSV not found: {decisions_path}")
    if output_path.exists() and not force:
        raise FileExistsError(f"Output already exists: {output_path}; pass --force to rebuild")

    decisions = read_decisions(decisions_path)
    decisions_checksum = sha256_file(decisions_path)
    canonical_checksum = sha256_file(canonical_path)
    applied_at = datetime.now(UTC).isoformat()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        prefix=output_path.stem + ".", suffix=".tmp.db", dir=output_path.parent, delete=False
    ) as handle:
        temporary_path = Path(handle.name)

    try:
        with closing(
            sqlite3.connect(readonly_sqlite_uri(canonical_path), uri=True)
        ) as source, closing(sqlite3.connect(temporary_path)) as target:
            source.execute("PRAGMA query_only = ON")
            source.backup(target)
            target.row_factory = sqlite3.Row
            target.execute("PRAGMA foreign_keys = ON")

            decision_counts = {decision: 0 for decision in sorted(DECISIONS)}
            for row in decisions:
                record = target.execute(
                    "SELECT * FROM constant_records WHERE record_id = ?", (row["record_id"],)
                ).fetchone()
                if record is None:
                    raise ValueError(f"Unknown record_id: {row['record_id']}")
                if record["verification_status"] in ("rejected", "superseded"):
                    raise ValueError(
                        f"Record is not reviewable in status {record['verification_status']}: "
                        f"{row['record_id']}"
                    )

                verified_reference_id = row["verified_reference_id"] or None
                supersedes_record_id = row["supersedes_record_id"] or None
                if verified_reference_id:
                    reference = target.execute(
                        "SELECT reference_id FROM source_references WHERE reference_id = ?",
                        (verified_reference_id,),
                    ).fetchone()
                    if reference is None:
                        raise ValueError(
                            f"Unknown verified_reference_id: {verified_reference_id}"
                        )
                    candidate_link = target.execute(
                        """
                        SELECT 1
                        FROM ligand_metal_reference_candidates
                        WHERE ligand_id = ? AND metal_species_id = ?
                          AND reference_id = ? AND resolution_status = 'resolved'
                        LIMIT 1
                        """,
                        (
                            record["ligand_id"],
                            record["metal_species_id"],
                            verified_reference_id,
                        ),
                    ).fetchone()
                    if candidate_link is None:
                        raise ValueError(
                            "verified_reference_id is not linked to the record's "
                            f"ligand-metal pair: {verified_reference_id}"
                        )
                if supersedes_record_id:
                    previous = target.execute(
                        """
                        SELECT record_id, ligand_id, metal_species_id, value_type
                        FROM constant_records WHERE record_id = ?
                        """,
                        (supersedes_record_id,),
                    ).fetchone()
                    if previous is None:
                        raise ValueError(
                            f"Unknown supersedes_record_id: {supersedes_record_id}"
                        )
                    current_identity = (
                        record["ligand_id"],
                        record["metal_species_id"],
                        record["value_type"],
                    )
                    previous_identity = (
                        previous["ligand_id"],
                        previous["metal_species_id"],
                        previous["value_type"],
                    )
                    if current_identity != previous_identity:
                        raise ValueError(
                            "A superseding record must have the same ligand, metal species, "
                            "and value type as the superseded record"
                        )

                is_active = 0 if row["decision"] == "rejected" else 1
                target.execute(
                    """
                    UPDATE constant_records
                    SET verification_status = ?, is_active = ?,
                        verified_reference_id = ?, supersedes_record_id = ?
                    WHERE record_id = ?
                    """,
                    (
                        row["decision"],
                        is_active,
                        verified_reference_id,
                        supersedes_record_id,
                        row["record_id"],
                    ),
                )
                if row["decision"] == "verified":
                    target.execute(
                        """
                        UPDATE source_references
                        SET verification_status = 'verified'
                        WHERE reference_id = ?
                        """,
                        (verified_reference_id,),
                    )
                if supersedes_record_id:
                    target.execute(
                        """
                        UPDATE constant_records
                        SET verification_status = 'superseded', is_active = 0
                        WHERE record_id = ?
                        """,
                        (supersedes_record_id,),
                    )

                target.execute(
                    """
                    INSERT INTO review_events (
                        review_id, record_id, decision, reviewer, reviewed_at_utc,
                        reason, verified_reference_id, supersedes_record_id,
                        decisions_file_sha256, applied_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["review_id"],
                        row["record_id"],
                        row["decision"],
                        row["reviewer"],
                        row["reviewed_at_utc"],
                        row["reason"],
                        verified_reference_id,
                        supersedes_record_id,
                        decisions_checksum,
                        applied_at,
                    ),
                )
                decision_counts[row["decision"]] += 1

            release_id = f"CURATED-{decisions_checksum[:16]}"
            reviewed_records = target.execute(
                """
                SELECT COUNT(*)
                FROM constant_records
                WHERE is_active = 1 AND verification_status IN ('reviewed', 'verified')
                """
            ).fetchone()[0]
            manifest = {
                "base_canonical_sha256": canonical_checksum,
                "decisions_file_sha256": decisions_checksum,
                "record_count": reviewed_records,
                "training_approved": False,
                "included_statuses": ["reviewed", "verified"],
            }
            target.execute(
                """
                INSERT INTO dataset_releases (
                    release_id, release_name, release_status, intended_use,
                    schema_version, created_at_utc, record_count, manifest_json
                ) VALUES (?, ?, 'reviewed', ?, '1.0.0', ?, ?, ?)
                """,
                (
                    release_id,
                    "Reviewed canonical stability-constant release",
                    "reviewed_records_not_automatically_approved_for_training",
                    applied_at,
                    reviewed_records,
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                ),
            )
            target.execute(
                """
                INSERT INTO dataset_release_records (release_id, record_id)
                SELECT ?, record_id
                FROM constant_records
                WHERE is_active = 1 AND verification_status IN ('reviewed', 'verified')
                """,
                (release_id,),
            )
            target.commit()
            integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_errors = len(target.execute("PRAGMA foreign_key_check").fetchall())
            if integrity != "ok":
                raise ValueError(f"Curated database failed integrity check: {integrity}")
            if foreign_key_errors:
                raise ValueError(
                    "Curated database failed foreign-key validation: "
                    f"{foreign_key_errors} error(s)"
                )
            status_counts = {
                row[0]: row[1]
                for row in target.execute(
                    "SELECT verification_status, COUNT(*) FROM constant_records GROUP BY verification_status"
                )
            }
            target.execute("ANALYZE")
            target.execute("VACUUM")

        temporary_path.replace(output_path)
        report = {
            "input": {
                "canonical_path": portable_report_path(canonical_path),
                "canonical_sha256": canonical_checksum,
                "decisions_path": portable_report_path(decisions_path),
                "decisions_sha256": decisions_checksum,
            },
            "output": {
                "path": portable_report_path(output_path),
                "sha256": sha256_file(output_path),
                "size_bytes": output_path.stat().st_size,
            },
            "release_id": release_id,
            "decision_counts": decision_counts,
            "status_counts": status_counts,
            "validation": {
                "sqlite_integrity": integrity,
                "foreign_key_errors": foreign_key_errors,
                "training_approved": False,
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
    parser.add_argument("--canonical", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = apply_reviews(
            args.canonical, args.decisions, args.output, args.report, force=args.force
        )
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Built: {report['output']['path']}")
    print(f"SHA-256: {report['output']['sha256']}")
    print(f"Release: {report['release_id']}")
    print(f"SQLite integrity: {report['validation']['sqlite_integrity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
