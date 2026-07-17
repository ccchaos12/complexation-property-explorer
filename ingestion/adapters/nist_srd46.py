"""NIST SRD 46 staging-to-canonical adapter."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .base import SourceAdapter


ADAPTER_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
STRICT_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?")
BATCH_SIZE = 5_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not STRICT_NUMBER.fullmatch(stripped):
        return None
    return float(stripped)


def canonical_id(prefix: str, source_record_id: int | str) -> str:
    return f"NIST_SRD46:{prefix}:{source_record_id}"


class NistSrd46Adapter(SourceAdapter):
    """Load the rebuilt NIST staging database into the canonical candidate schema."""

    @property
    def source_id(self) -> str:
        return "NIST_SRD46"

    def load(self, staging_path: Path, canonical_path: Path) -> dict:
        staging_checksum = sha256_file(staging_path)
        built_at = datetime.now(timezone.utc).isoformat()

        with closing(
            sqlite3.connect(f"file:{staging_path.resolve().as_posix()}?mode=ro", uri=True)
        ) as source, closing(sqlite3.connect(canonical_path)) as target:
            source.row_factory = sqlite3.Row
            source.execute("PRAGMA query_only = ON")
            target.execute("PRAGMA foreign_keys = ON")

            source_metadata = {
                row["key"]: row["value"]
                for row in source.execute("SELECT key, value FROM _build_metadata")
            }
            source_checksum = source_metadata["source_sha256"]
            source_version_id = f"NIST_SRD46:{source_checksum[:16]}"

            target.execute(
                """
                INSERT INTO sources (
                    source_id, source_name, source_type, publisher, doi,
                    license_url, source_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.source_id,
                    "NIST SRD 46 Version 8.0",
                    "legacy_sql_extraction",
                    "National Institute of Standards and Technology",
                    "10.18434/M32154",
                    "https://www.nist.gov/open/license",
                    "Third-party SQL extraction distributed by NIST AS IS. "
                    "Derived distributions must acknowledge NIST and state the "
                    "date and nature of modifications; see DATA_NOTICE.md.",
                ),
            )
            target.execute(
                """
                INSERT INTO source_versions (
                    source_version_id, source_id, version_label,
                    source_checksum_sha256, staging_checksum_sha256,
                    ingested_at_utc, adapter_name, adapter_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_version_id,
                    self.source_id,
                    "SRD 46 Version 8.0 / SQL package 2011",
                    source_checksum,
                    staging_checksum,
                    built_at,
                    type(self).__name__,
                    ADAPTER_VERSION,
                ),
            )

            metal_rows = source.execute(
                """
                SELECT metalID, name_metal, name_metal_pur, type, part_of, comment
                FROM metal ORDER BY metalID
                """
            )
            target.executemany(
                """
                INSERT INTO metal_species (
                    metal_species_id, source_version_id, source_record_id,
                    display_name_raw, source_code, species_type,
                    parent_source_record_id, source_comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        canonical_id("METAL", row["metalID"]),
                        source_version_id,
                        str(row["metalID"]),
                        row["name_metal"],
                        row["name_metal_pur"],
                        row["type"],
                        str(row["part_of"]) if row["part_of"] is not None else None,
                        row["comment"],
                    )
                    for row in metal_rows
                ),
            )

            ligand_rows = source.execute(
                """
                SELECT l.ligandenID, l.name_ligand, l.formula,
                       lc.name_ligandclass,
                       (
                         SELECT json_group_array(md.mol_string_encoded)
                         FROM mol_data AS md
                         WHERE md.ligandenNR = l.ligandenID
                       ) AS structure_raw,
                       l.comment
                FROM liganden AS l
                LEFT JOIN ligand_class AS lc ON lc.ligand_classID = l.ligand_classNr
                ORDER BY l.ligandenID
                """
            )
            target.executemany(
                """
                INSERT INTO ligands (
                    ligand_id, source_version_id, source_record_id,
                    ligand_name_raw, formula_raw, ligand_class_raw,
                    structure_raw, source_comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        canonical_id("LIGAND", row["ligandenID"]),
                        source_version_id,
                        str(row["ligandenID"]),
                        row["name_ligand"],
                        row["formula"],
                        row["name_ligandclass"],
                        row["structure_raw"],
                        row["comment"],
                    )
                    for row in ligand_rows
                ),
            )

            reference_rows = source.execute(
                """
                SELECT literature_altID, literature_shortcut, literature_alt, comment
                FROM literature_alt ORDER BY literature_altID
                """
            )
            target.executemany(
                """
                INSERT INTO source_references (
                    reference_id, source_version_id, source_record_id,
                    reference_code, citation_raw, source_comment
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        canonical_id("REFERENCE", row["literature_altID"]),
                        source_version_id,
                        str(row["literature_altID"]),
                        row["literature_shortcut"],
                        row["literature_alt"],
                        row["comment"],
                    )
                    for row in reference_rows
                ),
            )

            constants_query = source.execute(
                """
                SELECT v.verkn_ligand_metalID, v.ligandenNr, v.metalNr,
                       v.beta_definitionNr, bd.name_beta_definition,
                       ct.name_constanttyp, v.constant, v.constant_sic,
                       v.temperature, v.ionicstrength, s.name_solvent,
                       v.electrolyte, v.error, fn.name_footnote, v.comment
                FROM verkn_ligand_metal AS v
                JOIN constanttyp AS ct ON ct.constanttypID = v.constanttypNr
                LEFT JOIN beta_definition AS bd
                  ON bd.beta_definitionID = v.beta_definitionNr
                LEFT JOIN solvent AS s ON s.solventID = v.solventNr
                LEFT JOIN footnote AS fn ON fn.footnoteID = v.footnoteNr
                ORDER BY v.verkn_ligand_metalID
                """
            )
            insert_constant = """
                INSERT INTO constant_records (
                    record_id, source_version_id, source_record_id,
                    ligand_id, metal_species_id, equilibrium_raw, value_type,
                    reported_value_text, numeric_value,
                    source_standardized_value_text, temperature_raw,
                    temperature_c, temperature_k, ionic_strength_raw,
                    ionic_strength_numeric, solvent_raw, electrolyte_raw,
                    uncertainty_raw, footnote_raw, source_comment,
                    provenance_granularity, verification_status,
                    quality_flags_json, created_at_utc
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
            """
            flag_counts: dict[str, int] = {}
            constant_count = 0
            batch = []
            for row in constants_query:
                numeric_value = strict_float(row["constant"])
                temperature_c = strict_float(row["temperature"])
                ionic_strength = strict_float(row["ionicstrength"])
                flags = []
                if row["constant"] is not None and numeric_value is None:
                    flags.append("reported_value_not_strict_numeric")
                if row["beta_definitionNr"] not in (None, 0) and row["name_beta_definition"] is None:
                    flags.append("missing_equilibrium_definition")
                if row["name_constanttyp"] == "*":
                    flags.append("unclassified_value_type")
                for flag in flags:
                    flag_counts[flag] = flag_counts.get(flag, 0) + 1
                batch.append(
                    (
                        canonical_id("CONSTANT", row["verkn_ligand_metalID"]),
                        source_version_id,
                        str(row["verkn_ligand_metalID"]),
                        canonical_id("LIGAND", row["ligandenNr"]),
                        canonical_id("METAL", row["metalNr"]),
                        row["name_beta_definition"],
                        row["name_constanttyp"],
                        row["constant"],
                        numeric_value,
                        row["constant_sic"],
                        row["temperature"],
                        temperature_c,
                        temperature_c + 273.15 if temperature_c is not None else None,
                        row["ionicstrength"],
                        ionic_strength,
                        row["name_solvent"],
                        row["electrolyte"],
                        row["error"],
                        row["name_footnote"],
                        row["comment"],
                        "ligand_metal_candidate_references_only",
                        "candidate",
                        json.dumps(flags, separators=(",", ":")),
                        built_at,
                    )
                )
                if len(batch) >= BATCH_SIZE:
                    target.executemany(insert_constant, batch)
                    constant_count += len(batch)
                    batch.clear()
            if batch:
                target.executemany(insert_constant, batch)
                constant_count += len(batch)

            link_rows = source.execute(
                """
                SELECT verkn_ligand_metal_literatureID, ligandenNr, metalNr,
                       literature_altNr, not_used, comment
                FROM verkn_ligand_metal_literature
                ORDER BY verkn_ligand_metal_literatureID
                """
            )
            link_count = 0
            relationship_quality_counts = {"missing_reference": 0}
            batch = []
            insert_link = """
                INSERT INTO ligand_metal_reference_candidates (
                    link_id, source_version_id, source_record_id,
                    ligand_id, metal_species_id, reference_id,
                    resolution_status, not_used_flag, source_comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            for row in link_rows:
                has_reference = row["literature_altNr"] not in (None, 0)
                if not has_reference:
                    relationship_quality_counts["missing_reference"] += 1
                batch.append(
                    (
                        canonical_id("REFLINK", row["verkn_ligand_metal_literatureID"]),
                        source_version_id,
                        str(row["verkn_ligand_metal_literatureID"]),
                        canonical_id("LIGAND", row["ligandenNr"]),
                        canonical_id("METAL", row["metalNr"]),
                        canonical_id("REFERENCE", row["literature_altNr"])
                        if has_reference
                        else None,
                        "resolved" if has_reference else "missing_reference",
                        row["not_used"],
                        row["comment"],
                    )
                )
                if len(batch) >= BATCH_SIZE:
                    target.executemany(insert_link, batch)
                    link_count += len(batch)
                    batch.clear()
            if batch:
                target.executemany(insert_link, batch)
                link_count += len(batch)

            release_id = f"NIST_SRD46-CANDIDATES-{source_checksum[:12]}"
            manifest = {
                "source_version_id": source_version_id,
                "record_count": constant_count,
                "verification_status": "candidate",
                "record_level_provenance": "unresolved",
                "training_approved": False,
            }
            target.execute(
                """
                INSERT INTO dataset_releases (
                    release_id, release_name, release_status, intended_use,
                    schema_version, created_at_utc, record_count, manifest_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    release_id,
                    "NIST SRD 46 canonical candidate release",
                    "candidate",
                    "exploration_only_not_approved_for_model_training",
                    SCHEMA_VERSION,
                    built_at,
                    constant_count,
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                ),
            )
            target.execute(
                """
                INSERT INTO dataset_release_records (release_id, record_id)
                SELECT ?, record_id FROM constant_records
                """,
                (release_id,),
            )
            target.commit()

            counts = {
                "sources": target.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "source_versions": target.execute("SELECT COUNT(*) FROM source_versions").fetchone()[0],
                "metal_species": target.execute("SELECT COUNT(*) FROM metal_species").fetchone()[0],
                "ligands": target.execute("SELECT COUNT(*) FROM ligands").fetchone()[0],
                "references": target.execute("SELECT COUNT(*) FROM source_references").fetchone()[0],
                "constant_records": constant_count,
                "reference_candidate_links": link_count,
                "dataset_release_records": target.execute(
                    "SELECT COUNT(*) FROM dataset_release_records"
                ).fetchone()[0],
            }
            return {
                "adapter": type(self).__name__,
                "adapter_version": ADAPTER_VERSION,
                "schema_version": SCHEMA_VERSION,
                "source_id": self.source_id,
                "source_version_id": source_version_id,
                "source_checksum_sha256": source_checksum,
                "staging_checksum_sha256": staging_checksum,
                "release_id": release_id,
                "counts": counts,
                "quality_flag_counts": flag_counts,
                "relationship_quality_counts": relationship_quality_counts,
            }
