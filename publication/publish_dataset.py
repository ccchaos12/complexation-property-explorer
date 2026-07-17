#!/usr/bin/env python3
"""Publish an immutable, verified-only machine-learning dataset and manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from complexation_explorer.io_utils import readonly_sqlite_uri, require_distinct_paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def portable_report_path(path: Path) -> str:
    """Return a repository-relative path without exposing a local home directory."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return f"<external>/{path.name}"


APPROVAL_FIELDS = {
    "publication_id",
    "approver",
    "approved_at_utc",
    "purpose",
    "allowed_statuses",
    "require_numeric_value",
    "require_verified_reference",
}
EXPORT_COLUMNS = (
    "record_id",
    "source_id",
    "source_name",
    "source_version_id",
    "source_version_label",
    "source_record_id",
    "ligand_id",
    "ligand_name",
    "ligand_formula",
    "ligand_class",
    "metal_species_id",
    "metal_species",
    "metal_code",
    "equilibrium",
    "value_type",
    "reported_value",
    "numeric_value",
    "temperature_raw",
    "temperature_c",
    "temperature_k",
    "ionic_strength_raw",
    "ionic_strength_numeric",
    "solvent",
    "electrolyte",
    "uncertainty",
    "verification_status",
    "verified_reference_id",
    "reference_code",
    "verified_reference",
    "quality_flags_json",
)


def _replace_output_pair(replacements: tuple[tuple[Path, Path], ...]) -> None:
    """Install related outputs together and restore previous files on failure."""
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for _, target in replacements:
            if target.exists():
                backup = target.with_name(f".{target.name}.{uuid4().hex}.backup")
                os.replace(target, backup)
                backups[target] = backup
        for temporary, target in replacements:
            os.replace(temporary, target)
            installed.append(target)
    except Exception as error:
        rollback_errors = []
        for target in reversed(installed):
            try:
                target.unlink(missing_ok=True)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        for target, backup in backups.items():
            try:
                os.replace(backup, target)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise RuntimeError(
                "Output installation failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from error
        raise
    else:
        for backup in backups.values():
            backup.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("approved_at_utc must include a UTC offset")
    return parsed.astimezone(UTC).isoformat()


def build_data_terms(source_rows: list[sqlite3.Row]) -> list[dict]:
    """Build source-specific distribution metadata for the published records."""
    terms = []
    for row in source_rows:
        item = {
            "source_id": row["source_id"],
            "source_name": row["source_name"],
            "doi": row["doi"],
            "terms_url": row["license_url"],
        }
        if row["source_id"] == "NIST_SRD46":
            item.update(
                {
                    "source_record_url": "https://data.nist.gov/od/id/mds2-2154",
                    "modification_notice": "DATA_NOTICE.md",
                    "distribute_notice_with_dataset": True,
                }
            )
        else:
            item["distribution_review_required"] = True
        terms.append(item)
    return terms


def read_approval(path: Path) -> dict:
    approval = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(approval, dict) or set(approval) != APPROVAL_FIELDS:
        raise ValueError(
            "Approval JSON fields must match the template exactly: "
            + ", ".join(sorted(APPROVAL_FIELDS))
        )
    for field in ("publication_id", "approver", "approved_at_utc", "purpose"):
        if not isinstance(approval[field], str) or not approval[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
        approval[field] = approval[field].strip()
    approval["approved_at_utc"] = parse_utc(approval["approved_at_utc"])
    if approval["allowed_statuses"] != ["verified"]:
        raise ValueError("allowed_statuses must be exactly ['verified']")
    if approval["require_numeric_value"] is not True:
        raise ValueError("require_numeric_value must be true")
    if approval["require_verified_reference"] is not True:
        raise ValueError("require_verified_reference must be true")
    return approval


PUBLISH_QUERY = """
    SELECT c.record_id,
           s.source_id,
           s.source_name,
           sv.source_version_id,
           sv.version_label AS source_version_label,
           c.source_record_id,
           l.ligand_id,
           l.ligand_name_raw AS ligand_name,
           l.formula_raw AS ligand_formula,
           l.ligand_class_raw AS ligand_class,
           m.metal_species_id,
           m.display_name_raw AS metal_species,
           m.source_code AS metal_code,
           c.equilibrium_raw AS equilibrium,
           c.value_type,
           c.reported_value_text AS reported_value,
           c.numeric_value,
           c.temperature_raw,
           c.temperature_c,
           c.temperature_k,
           c.ionic_strength_raw,
           c.ionic_strength_numeric,
           c.solvent_raw AS solvent,
           c.electrolyte_raw AS electrolyte,
           c.uncertainty_raw AS uncertainty,
           c.verification_status,
           c.verified_reference_id,
           r.reference_code,
           r.citation_raw AS verified_reference,
           c.quality_flags_json
    FROM constant_records AS c
    JOIN source_versions AS sv ON sv.source_version_id = c.source_version_id
    JOIN sources AS s ON s.source_id = sv.source_id
    JOIN ligands AS l ON l.ligand_id = c.ligand_id
    JOIN metal_species AS m ON m.metal_species_id = c.metal_species_id
    JOIN source_references AS r ON r.reference_id = c.verified_reference_id
    WHERE c.is_active = 1
      AND c.verification_status = 'verified'
      AND c.numeric_value IS NOT NULL
      AND c.verified_reference_id IS NOT NULL
      AND r.verification_status = 'verified'
    ORDER BY c.record_id
"""


def publish_dataset(
    database_path: Path,
    approval_path: Path,
    output_path: Path,
    manifest_path: Path,
    *,
    force: bool = False,
) -> dict:
    database_path = database_path.resolve()
    approval_path = approval_path.resolve()
    output_path = output_path.resolve()
    manifest_path = manifest_path.resolve()
    require_distinct_paths(
        database=database_path,
        approval=approval_path,
        output=output_path,
        manifest=manifest_path,
    )
    if not database_path.is_file():
        raise FileNotFoundError(f"Curated database not found: {database_path}")
    if not approval_path.is_file():
        raise FileNotFoundError(f"Approval JSON not found: {approval_path}")
    if not force and (output_path.exists() or manifest_path.exists()):
        raise FileExistsError("Output or manifest already exists; pass --force to replace both")

    approval = read_approval(approval_path)
    database_checksum = sha256_file(database_path)
    approval_checksum = sha256_file(approval_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(
        sqlite3.connect(readonly_sqlite_uri(database_path), uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Curated database failed integrity check: {integrity}")
        foreign_key_error = connection.execute("PRAGMA foreign_key_check").fetchone()
        if foreign_key_error:
            raise ValueError("Curated database failed foreign-key validation")
        rows = connection.execute(PUBLISH_QUERY).fetchall()
        source_ids = sorted({row["source_id"] for row in rows})
        placeholders = ", ".join("?" for _ in source_ids)
        source_rows = (
            connection.execute(
                f"""
                SELECT source_id, source_name, doi, license_url
                FROM sources
                WHERE source_id IN ({placeholders})
                ORDER BY source_id
                """,  # noqa: S608 -- Placeholder count is derived from trusted row count.
                source_ids,
            ).fetchall()
            if source_ids
            else []
        )
    if not rows:
        raise ValueError("No verified records satisfy the publication requirements")

    temporary_path: Path | None = None
    temporary_manifest_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=output_path.stem + ".",
            suffix=".tmp.csv",
            dir=output_path.parent,
            delete=False,
        ) as temporary_handle:
            temporary_path = Path(temporary_handle.name)
            writer = csv.DictWriter(temporary_handle, fieldnames=EXPORT_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        output_checksum = sha256_file(temporary_path)
        published_at = datetime.now(UTC).isoformat()
        manifest = {
            "publication_id": approval["publication_id"],
            "training_approved": True,
            "purpose": approval["purpose"],
            "approval": {
                "approver": approval["approver"],
                "approved_at_utc": approval["approved_at_utc"],
                "approval_file_sha256": approval_checksum,
            },
            "source": {
                "database_path": portable_report_path(database_path),
                "database_sha256": database_checksum,
                "opened_read_only": True,
            },
            "output": {
                "dataset_path": portable_report_path(output_path),
                "dataset_sha256": output_checksum,
                "format": "CSV UTF-8",
                "record_count": len(rows),
                "columns": list(EXPORT_COLUMNS),
            },
            "selection_rules": {
                "is_active": True,
                "allowed_statuses": ["verified"],
                "numeric_value_required": True,
                "verified_reference_required": True,
                "verified_reference_status_required": True,
            },
            "data_terms": build_data_terms(source_rows),
            "published_at_utc": published_at,
            "local_excel_accessed": False,
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=manifest_path.stem + ".",
            suffix=".tmp.json",
            dir=manifest_path.parent,
            delete=False,
        ) as temporary_manifest_handle:
            temporary_manifest_path = Path(temporary_manifest_handle.name)
            temporary_manifest_handle.write(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
            )
        _replace_output_pair(
            (
                (temporary_path, output_path),
                (temporary_manifest_path, manifest_path),
            )
        )
        return manifest
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if temporary_manifest_path is not None:
            temporary_manifest_path.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = publish_dataset(
            args.database, args.approval, args.output, args.manifest, force=args.force
        )
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Published: {manifest['output']['dataset_path']}")
    print(f"Records: {manifest['output']['record_count']}")
    print(f"SHA-256: {manifest['output']['dataset_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
