"""Parameterized, read-only queries for the canonical stability-constant database."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .io_utils import readonly_sqlite_uri

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = (
    PROJECT_ROOT / "data/generated/Complexation_Constants_Unified_rebuilt.db"
)
VALUE_TYPES = {"K", "H", "S", "*"}
MAX_QUERY_LIMIT = 50_000
CANONICAL_SCHEMA_VERSION = "2"
REACTION_TYPE_LABELS = {
    "complex_1_1": "1:1 complex · M + L ⇌ ML",
    "complex_1_2": "1:2 complex · M + 2 L ⇌ ML₂",
    "complex_1_3": "1:3 complex · M + 3 L ⇌ ML₃",
    "complex_1_4": "1:4 complex · M + 4 L ⇌ ML₄",
    "protonation": "Ligand protonation",
    "hydrolysis": "Hydrolysis / hydroxide-coupled",
    "phase": "Precipitation / dissolution",
    "other": "Other coupled equilibrium",
}

REACTION_CLASS_SQL = """
CASE
  WHEN v.equilibrium_raw = '[ML]/[M][L]' THEN 'complex_1_1'
  WHEN v.equilibrium_raw = '[ML<sub>2</sub>]/[M][L]<sup>2</sup>' THEN 'complex_1_2'
  WHEN v.equilibrium_raw = '[ML<sub>3</sub>]/[M][L]<sup>3</sup>' THEN 'complex_1_3'
  WHEN v.equilibrium_raw = '[ML<sub>4</sub>]/[M][L]<sup>4</sup>' THEN 'complex_1_4'
  WHEN LOWER(COALESCE(v.equilibrium_raw, '')) LIKE '%(s)%' THEN 'phase'
  WHEN UPPER(COALESCE(v.equilibrium_raw, '')) LIKE '%OH%' THEN 'hydrolysis'
  WHEN INSTR(COALESCE(v.equilibrium_raw, ''), '[M') = 0
       AND INSTR(COALESCE(v.equilibrium_raw, ''), '[H') > 0 THEN 'protonation'
  ELSE 'other'
END
"""


@dataclass(frozen=True)
class SearchFilters:
    metal_ids: tuple[str, ...] = ()
    ligand_text: str = ""
    ligand_classes: tuple[str, ...] = ()
    value_type: str = "K"
    value_min: float | None = None
    value_max: float | None = None
    temperature_c_min: float | None = None
    temperature_c_max: float | None = None
    ionic_strength_min: float | None = None
    ionic_strength_max: float | None = None
    numeric_only: bool = False
    reaction_types: tuple[str, ...] = ()
    include_strict_duplicates: bool = False


def resolve_database_path(path: str | Path | None = None) -> Path:
    configured = path or os.environ.get("COMPLEXATION_DB_PATH") or DEFAULT_DB_PATH
    database_path = Path(configured).expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Canonical SQLite database not found: {database_path}")
    return database_path


def connect_readonly(path: str | Path | None = None) -> sqlite3.Connection:
    database_path = resolve_database_path(path)
    connection = sqlite3.connect(
        readonly_sqlite_uri(database_path),
        uri=True,
        timeout=10,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _rows_as_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_range(
    minimum: float | None,
    maximum: float | None,
    label: str,
) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"{label} minimum cannot exceed maximum")


def _build_where(filters: SearchFilters) -> tuple[str, list]:
    clauses = []
    parameters: list = []

    if filters.metal_ids:
        placeholders = ", ".join("?" for _ in filters.metal_ids)
        clauses.append(f"m.metal_species_id IN ({placeholders})")
        parameters.extend(filters.metal_ids)
    if filters.value_type not in VALUE_TYPES:
        raise ValueError(f"Unsupported value type: {filters.value_type}")
    clauses.append("v.value_type = ?")
    parameters.append(filters.value_type)

    _validate_range(filters.value_min, filters.value_max, "Value")
    _validate_range(
        filters.temperature_c_min,
        filters.temperature_c_max,
        "Temperature",
    )
    _validate_range(
        filters.ionic_strength_min,
        filters.ionic_strength_max,
        "Ionic strength",
    )

    range_filters = (
        ("v.numeric_value", filters.value_min, filters.value_max),
        ("v.temperature_c", filters.temperature_c_min, filters.temperature_c_max),
        (
            "v.ionic_strength_numeric",
            filters.ionic_strength_min,
            filters.ionic_strength_max,
        ),
    )
    for column, minimum, maximum in range_filters:
        if minimum is not None:
            clauses.append(f"{column} >= ?")
            parameters.append(minimum)
        if maximum is not None:
            clauses.append(f"{column} <= ?")
            parameters.append(maximum)

    if filters.numeric_only:
        clauses.append("v.numeric_value IS NOT NULL")

    if not filters.include_strict_duplicates:
        clauses.append(
            """
            NOT EXISTS (
                SELECT 1
                FROM constant_record_relationships AS relationship
                WHERE relationship.duplicate_record_id = v.record_id
                  AND relationship.relationship_type
                    = 'strict_cross_source_duplicate'
            )
            """
        )

    if filters.reaction_types:
        unsupported_reactions = set(filters.reaction_types) - set(
            REACTION_TYPE_LABELS
        )
        if unsupported_reactions:
            raise ValueError(
                "Unsupported reaction type: "
                + ", ".join(sorted(unsupported_reactions))
            )
        placeholders = ", ".join("?" for _ in filters.reaction_types)
        clauses.append(f"({REACTION_CLASS_SQL}) IN ({placeholders})")
        parameters.extend(filters.reaction_types)

    if filters.ligand_text.strip():
        clauses.append("LOWER(l.ligand_name_raw) LIKE ? ESCAPE '\\'")
        parameters.append(f"%{_escape_like(filters.ligand_text.strip().lower())}%")

    if filters.ligand_classes:
        placeholders = ", ".join("?" for _ in filters.ligand_classes)
        clauses.append(f"l.ligand_class_raw IN ({placeholders})")
        parameters.extend(filters.ligand_classes)

    return " AND ".join(clauses), parameters


BASE_FROM = """
    FROM active_constant_records AS v
    JOIN ligands AS l ON l.ligand_id = v.ligand_id
    JOIN metal_species AS m ON m.metal_species_id = v.metal_species_id
    JOIN source_versions AS sv ON sv.source_version_id = v.source_version_id
    JOIN sources AS s ON s.source_id = sv.source_id
"""


def list_metals(path: str | Path | None = None) -> list[dict]:
    with closing(connect_readonly(path)) as connection:
        rows = connection.execute(
            """
            SELECT metal_species_id AS metal_id,
                   display_name_raw AS metal_name,
                   source_code AS metal_code
            FROM metal_species
            ORDER BY LOWER(source_code), metal_species_id
            """
        ).fetchall()
    return _rows_as_dicts(rows)


def list_ligand_classes(path: str | Path | None = None) -> list[str]:
    with closing(connect_readonly(path)) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT ligand_class_raw
            FROM ligands
            WHERE ligand_class_raw IS NOT NULL
            ORDER BY LOWER(ligand_class_raw)
            """
        ).fetchall()
    return [row[0] for row in rows if row[0]]


def count_constants(
    filters: SearchFilters, path: str | Path | None = None
) -> int:
    where_sql, parameters = _build_where(filters)
    with closing(connect_readonly(path)) as connection:
        return connection.execute(
            f"SELECT COUNT(*) {BASE_FROM} WHERE {where_sql}", parameters
        ).fetchone()[0]


def search_constants(
    filters: SearchFilters,
    path: str | Path | None = None,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    if not 1 <= limit <= MAX_QUERY_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_QUERY_LIMIT}")
    if offset < 0:
        raise ValueError("offset cannot be negative")

    where_sql, parameters = _build_where(filters)
    query = f"""
        SELECT v.record_id,
               s.source_id,
               s.source_name,
               sv.version_label AS source_version,
               m.metal_species_id AS metal_id,
               m.display_name_raw AS metal,
               l.ligand_id,
               l.ligand_name_raw AS ligand,
               l.formula_raw AS formula,
               l.ligand_class_raw AS ligand_class,
               v.equilibrium_raw AS equilibrium,
               v.temperature_raw AS temperature,
               v.temperature_k,
               v.ionic_strength_raw AS ionic_strength,
               v.ionic_strength_numeric,
               v.solvent_raw AS solvent,
               v.electrolyte_raw AS electrolyte,
               v.value_type,
               v.reported_value_text AS reported_value,
               v.numeric_value,
               v.source_standardized_value_text AS standardized_value,
               v.uncertainty_raw AS error,
               v.footnote_raw AS footnote,
               v.quality_flags_json,
               {REACTION_CLASS_SQL} AS reaction_type,
               (
                 SELECT COUNT(DISTINCT link.reference_id)
                 FROM ligand_metal_reference_candidates AS link
                 WHERE link.ligand_id = v.ligand_id
                   AND link.metal_species_id = v.metal_species_id
                   AND link.resolution_status = 'resolved'
               ) AS candidate_reference_count
        {BASE_FROM}
        WHERE {where_sql}
        ORDER BY LOWER(m.source_code), LOWER(l.ligand_name_raw),
                 v.numeric_value, v.record_id
        LIMIT ? OFFSET ?
    """  # noqa: S608 -- Only fixed SQL fragments and placeholders are interpolated.
    parameters.extend((limit, offset))
    with closing(connect_readonly(path)) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return _rows_as_dicts(rows)


def search_record_ids(
    query: str,
    path: str | Path | None = None,
    *,
    limit: int = 25,
    exclude_record_id: str | None = None,
) -> list[dict]:
    """Find active records by a case-insensitive Record ID substring."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    escaped_query = _escape_like(normalized_query)
    contains_pattern = f"%{escaped_query}%"
    prefix_pattern = f"{escaped_query}%"
    exclude_sql = ""
    parameters: list = [contains_pattern]
    if exclude_record_id:
        exclude_sql = "AND v.record_id <> ?"
        parameters.append(exclude_record_id)
    parameters.extend((normalized_query, prefix_pattern, limit))

    with closing(connect_readonly(path)) as connection:
        rows = connection.execute(
            f"""
            SELECT v.record_id,
                   s.source_id,
                   s.source_name,
                   m.display_name_raw AS metal,
                   l.ligand_name_raw AS ligand,
                   l.formula_raw AS formula,
                   v.value_type,
                   v.reported_value_text AS reported_value,
                   v.temperature_raw AS temperature,
                   v.ionic_strength_raw AS ionic_strength
            {BASE_FROM}
            WHERE LOWER(v.record_id) LIKE ? ESCAPE '\\'
              {exclude_sql}
            ORDER BY CASE
                       WHEN LOWER(v.record_id) = ? THEN 0
                       WHEN LOWER(v.record_id) LIKE ? ESCAPE '\\' THEN 1
                       ELSE 2
                     END,
                     LENGTH(v.record_id), v.record_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    return _rows_as_dicts(rows)


def get_record_detail(
    record_id: str, path: str | Path | None = None
) -> dict | None:
    with closing(connect_readonly(path)) as connection:
        row = connection.execute(
            f"""
            SELECT v.*, m.display_name_raw AS metal, m.source_code AS metal_code,
                   l.ligand_name_raw AS ligand, l.formula_raw AS formula,
                   l.ligand_class_raw AS ligand_class,
                   s.source_id, s.source_name,
                   sv.version_label AS source_version
            {BASE_FROM}
            WHERE v.record_id = ?
            """,
            (record_id,),
        ).fetchone()
    return dict(row) if row else None


def get_candidate_references(
    ligand_id: str, metal_id: str, path: str | Path | None = None
) -> list[dict]:
    with closing(connect_readonly(path)) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT r.reference_id,
                            r.reference_code,
                            r.citation_raw AS reference_text,
                            link.not_used_flag AS not_used,
                            link.source_comment AS comment
            FROM ligand_metal_reference_candidates AS link
            JOIN source_references AS r ON r.reference_id = link.reference_id
            WHERE link.ligand_id = ?
              AND link.metal_species_id = ?
              AND link.resolution_status = 'resolved'
            ORDER BY r.reference_code, r.reference_id
            """,
            (ligand_id, metal_id),
        ).fetchall()
    return _rows_as_dicts(rows)


def get_record_relationships(
    record_id: str, path: str | Path | None = None
) -> list[dict]:
    """Return strict duplicate relationships involving one source record."""
    with closing(connect_readonly(path)) as connection:
        rows = connection.execute(
            """
            SELECT relationship_id, duplicate_record_id, preferred_record_id,
                   relationship_type, evidence_json,
                   CASE
                     WHEN duplicate_record_id = ? THEN 'duplicate'
                     ELSE 'preferred'
                   END AS record_role
            FROM constant_record_relationships
            WHERE duplicate_record_id = ? OR preferred_record_id = ?
            ORDER BY relationship_id
            """,
            (record_id, record_id, record_id),
        ).fetchall()
    return _rows_as_dicts(rows)


def get_ligand_identity_matches(
    ligand_id: str, path: str | Path | None = None
) -> list[dict]:
    """Return exact-structure ligand identity relationships."""
    with closing(connect_readonly(path)) as connection:
        rows = connection.execute(
            """
            SELECT relationship.identity_relationship_id,
                   relationship.source_ligand_id,
                   source_ligand.ligand_name_raw AS source_ligand_name,
                   relationship.matched_ligand_id,
                   matched_ligand.ligand_name_raw AS matched_ligand_name,
                   relationship.relationship_type,
                   relationship.evidence_json
            FROM ligand_identity_relationships AS relationship
            JOIN ligands AS source_ligand
              ON source_ligand.ligand_id = relationship.source_ligand_id
            JOIN ligands AS matched_ligand
              ON matched_ligand.ligand_id = relationship.matched_ligand_id
            WHERE relationship.source_ligand_id = ?
               OR relationship.matched_ligand_id = ?
            ORDER BY relationship.identity_relationship_id
            """,
            (ligand_id, ligand_id),
        ).fetchall()
    return _rows_as_dicts(rows)


def get_database_summary(path: str | Path | None = None) -> dict:
    database_path = resolve_database_path(path)
    with closing(connect_readonly(database_path)) as connection:
        source_versions = connection.execute(
            """
            SELECT sv.*, s.source_name, s.doi, s.license_url
            FROM source_versions AS sv
            JOIN sources AS s ON s.source_id = sv.source_id
            ORDER BY sv.ingested_at_utc, sv.source_version_id
            """
        ).fetchall()
        if not source_versions:
            raise ValueError("The database has no source version metadata")
        totals = connection.execute(
            """
            SELECT (SELECT COUNT(*) FROM metal_species) AS metals,
                   (SELECT COUNT(*) FROM ligands) AS ligands,
                   (SELECT COUNT(*) FROM active_constant_records) AS constants,
                   (
                     SELECT COUNT(*) FROM deduplicated_active_constant_records
                   ) AS deduplicated_constants,
                   (
                     SELECT COUNT(*) FROM constant_record_relationships
                     WHERE relationship_type = 'strict_cross_source_duplicate'
                   ) AS strict_duplicate_records,
                   (
                     SELECT COUNT(*) FROM ligand_identity_relationships
                     WHERE relationship_type = 'exact_structure'
                   ) AS exact_structure_ligand_links,
                   (SELECT COUNT(*) FROM source_references) AS references_count
            """
        ).fetchone()
        log_k = connection.execute(
            "SELECT COUNT(*) FROM active_constant_records WHERE value_type = 'K'"
        ).fetchone()[0]
        deduplicated_log_k = connection.execute(
            """
            SELECT COUNT(*) FROM deduplicated_active_constant_records
            WHERE value_type = 'K'
            """
        ).fetchone()[0]
        database_user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        latest_release = connection.execute(
            """
            SELECT release_id, release_name, schema_version, created_at_utc
            FROM dataset_releases
            ORDER BY created_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
    source_metadata = [dict(row) for row in source_versions]
    source_ids = sorted({row["source_id"] for row in source_metadata})
    version_labels = list(dict.fromkeys(row["version_label"] for row in source_metadata))
    built_at_utc = max(row["ingested_at_utc"] for row in source_metadata)
    schema_version = (
        latest_release["schema_version"]
        if latest_release
        else str(database_user_version or CANONICAL_SCHEMA_VERSION)
    )
    return {
        **dict(totals),
        "log_k": log_k,
        "deduplicated_log_k": deduplicated_log_k,
        "sources": source_metadata,
        "source_ids": source_ids,
        "source_count": len(source_ids),
        "dataset_version": " + ".join(version_labels),
        "built_at_utc": built_at_utc,
        "database_sha256": _sha256_file(database_path),
        "schema_version": schema_version,
        "latest_release": dict(latest_release) if latest_release else None,
    }
