"""Local Excel supplement staging-to-canonical adapter."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from complexation_explorer.io_utils import readonly_sqlite_uri

from .base import SourceAdapter
from .nist_srd46 import sha256_file, strict_float

ADAPTER_VERSION = "1.0.0"
SOURCE_ID = "SUPPLEMENT"
BATCH_SIZE = 1_000


def canonical_id(prefix: str, source_record_id: int | str) -> str:
    return f"{SOURCE_ID}:{prefix}:{source_record_id}"


class LocalExcelSupplementAdapter(SourceAdapter):
    """Load the immutable NIST-shaped local Excel supplement."""

    @property
    def source_id(self) -> str:
        return SOURCE_ID

    def load(self, staging_path: Path, canonical_path: Path) -> dict:
        staging_checksum = sha256_file(staging_path)
        built_at = datetime.now(UTC).isoformat()

        with closing(
            sqlite3.connect(readonly_sqlite_uri(staging_path), uri=True)
        ) as source, closing(sqlite3.connect(canonical_path)) as target:
            source.row_factory = sqlite3.Row
            source.execute("PRAGMA query_only = ON")
            target.row_factory = sqlite3.Row
            target.execute("PRAGMA foreign_keys = ON")

            source_metadata = {
                row["key"]: row["value"]
                for row in source.execute("SELECT key, value FROM _build_metadata")
            }
            source_checksum = source_metadata["source_sha256"]
            source_version_id = f"{SOURCE_ID}:{source_checksum[:16]}"

            target.execute(
                """
                INSERT INTO sources (
                    source_id, source_name, source_type, publisher, doi,
                    license_url, source_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.source_id,
                    "Local Excel NIST SRD 46 Supplement",
                    "verified_excel_supplement",
                    None,
                    None,
                    None,
                    "Converted from the project owner's local Excel database. "
                    "All imported records are declared verified for application use. "
                    f"Original workbook: {source_metadata.get('source_filename', 'unknown')}.",
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
                    "Local Excel supplement 2026-07-19",
                    source_checksum,
                    staging_checksum,
                    built_at,
                    type(self).__name__,
                    ADAPTER_VERSION,
                ),
            )

            used_metal_ids = {
                row[0]
                for row in source.execute(
                    """
                    SELECT metalNr FROM verkn_ligand_metal
                    UNION
                    SELECT metalNr FROM verkn_ligand_metal_literature
                    """
                )
                if row[0] is not None
            }
            missing_metals = [
                metal_id
                for metal_id in sorted(used_metal_ids)
                if target.execute(
                    "SELECT 1 FROM metal_species WHERE metal_species_id = ?",
                    (f"NIST_SRD46:METAL:{metal_id}",),
                ).fetchone()
                is None
            ]
            if missing_metals:
                raise ValueError(
                    "Supplement contains metal IDs not present in canonical NIST data: "
                    + ", ".join(map(str, missing_metals))
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
                    structure_raw, identity_status, source_comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        "verified",
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
                    reference_code, citation_raw, verification_status,
                    source_comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        canonical_id("REFERENCE", row["literature_altID"]),
                        source_version_id,
                        str(row["literature_altID"]),
                        row["literature_shortcut"],
                        row["literature_alt"],
                        "verified",
                        row["comment"],
                    )
                    for row in reference_rows
                ),
            )

            exact_reference_rows = source.execute(
                """
                SELECT verkn_ligand_metalNr, literature_altNr
                FROM verkn_ligand_metal_literature_sic
                ORDER BY verkn_ligand_metalNr
                """
            ).fetchall()
            exact_references: dict[int, int] = {}
            for row in exact_reference_rows:
                constant_id = row["verkn_ligand_metalNr"]
                reference_id = row["literature_altNr"]
                if constant_id in exact_references:
                    raise ValueError(
                        "Supplement constant has more than one exact reference: "
                        f"{constant_id}"
                    )
                if reference_id in (None, 0):
                    raise ValueError(
                        f"Supplement constant has no exact verified reference: {constant_id}"
                    )
                exact_references[constant_id] = reference_id

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
                    quality_flags_json, verified_reference_id, created_at_utc
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
            """
            flag_counts: dict[str, int] = {}
            constant_count = 0
            batch = []
            for row in constants_query:
                source_record_id = row["verkn_ligand_metalID"]
                reference_source_id = exact_references.get(source_record_id)
                if reference_source_id is None:
                    raise ValueError(
                        f"Supplement constant has no exact reference link: {source_record_id}"
                    )
                numeric_value = strict_float(row["constant"])
                temperature_c = strict_float(row["temperature"])
                ionic_strength = strict_float(row["ionicstrength"])
                flags = []
                if row["constant"] is not None and numeric_value is None:
                    flags.append("reported_value_not_strict_numeric")
                if (
                    row["beta_definitionNr"] not in (None, 0)
                    and row["name_beta_definition"] is None
                ):
                    flags.append("missing_equilibrium_definition")
                if row["name_constanttyp"] == "*":
                    flags.append("unclassified_value_type")
                for flag in flags:
                    flag_counts[flag] = flag_counts.get(flag, 0) + 1
                batch.append(
                    (
                        canonical_id("CONSTANT", source_record_id),
                        source_version_id,
                        str(source_record_id),
                        canonical_id("LIGAND", row["ligandenNr"]),
                        f"NIST_SRD46:METAL:{row['metalNr']}",
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
                        "record_level_verified_reference",
                        "verified",
                        json.dumps(flags, separators=(",", ":")),
                        canonical_id("REFERENCE", reference_source_id),
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

            if constant_count != len(exact_references):
                raise ValueError(
                    "Supplement constant/reference count mismatch: "
                    f"{constant_count} constants and {len(exact_references)} exact references"
                )

            link_rows = source.execute(
                """
                SELECT verkn_ligand_metal_literatureID, ligandenNr, metalNr,
                       literature_altNr, not_used, comment
                FROM verkn_ligand_metal_literature
                ORDER BY verkn_ligand_metal_literatureID
                """
            )
            link_count = 0
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
                batch.append(
                    (
                        canonical_id(
                            "REFLINK", row["verkn_ligand_metal_literatureID"]
                        ),
                        source_version_id,
                        str(row["verkn_ligand_metal_literatureID"]),
                        canonical_id("LIGAND", row["ligandenNr"]),
                        f"NIST_SRD46:METAL:{row['metalNr']}",
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

            target.commit()
            counts = {
                "sources": 1,
                "source_versions": 1,
                "metals_reused_from_nist": len(used_metal_ids),
                "ligands": target.execute(
                    "SELECT COUNT(*) FROM ligands WHERE source_version_id = ?",
                    (source_version_id,),
                ).fetchone()[0],
                "references": target.execute(
                    "SELECT COUNT(*) FROM source_references WHERE source_version_id = ?",
                    (source_version_id,),
                ).fetchone()[0],
                "constant_records": constant_count,
                "reference_candidate_links": link_count,
                "exact_verified_reference_links": len(exact_references),
            }
            return {
                "adapter": type(self).__name__,
                "adapter_version": ADAPTER_VERSION,
                "source_id": self.source_id,
                "source_version_id": source_version_id,
                "source_checksum_sha256": source_checksum,
                "staging_checksum_sha256": staging_checksum,
                "counts": counts,
                "quality_flag_counts": flag_counts,
            }
