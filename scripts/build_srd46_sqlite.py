#!/usr/bin/env python3
"""Build a reproducible SQLite database from NIST's SRD 46 SQL archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_ROOT))

from complexation_explorer.io_utils import require_distinct_paths  # noqa: E402


EXPECTED_ARCHIVE_SHA256 = (
    "141269bb8c6d9e8271a5b4bff35f7c9fa913938bb50a62c096847de67e382d18"
)
BUILDER_VERSION = "1.0.0"
BATCH_SIZE = 5_000


def portable_report_path(path: Path) -> str:
    """Return a repository-relative path without exposing a local home directory."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return f"<external>/{resolved.name}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sqlite_type(mysql_type: str) -> str:
    value = mysql_type.lower()
    if value.startswith(("int", "tinyint", "smallint", "mediumint", "bigint")):
        return "INTEGER"
    if value.startswith(("float", "double", "decimal", "numeric", "real")):
        return "REAL"
    if value.startswith(("blob", "binary", "varbinary")):
        return "BLOB"
    return "TEXT"


def parse_mysql_schema(sql_text: str) -> dict:
    table_match = re.search(r"CREATE TABLE\s+`([^`]+)`\s*\(", sql_text)
    if not table_match:
        raise ValueError("CREATE TABLE statement not found")
    table_name = table_match.group(1)
    body_start = table_match.end()
    body_end = sql_text.find(") ENGINE=", body_start)
    if body_end < 0:
        raise ValueError(f"End of CREATE TABLE not found for {table_name}")
    body = sql_text[body_start:body_end]

    columns = []
    primary_key = None
    indexes = []
    for line in body.splitlines():
        column_match = re.match(r"\s*`([^`]+)`\s+([^\s,]+)", line)
        if column_match:
            columns.append(
                {
                    "name": column_match.group(1),
                    "mysql_type": column_match.group(2),
                    "sqlite_type": sqlite_type(column_match.group(2)),
                }
            )
            continue
        primary_match = re.match(r"\s*PRIMARY KEY\s*\(`([^`]+)`\)", line)
        if primary_match:
            primary_key = primary_match.group(1)
            continue
        index_match = re.match(r"\s*KEY\s+`([^`]+)`\s*\(([^)]+)\)", line)
        if index_match:
            index_columns = re.findall(r"`([^`]+)`", index_match.group(2))
            if index_columns:
                indexes.append({"name": index_match.group(1), "columns": index_columns})

    if not columns:
        raise ValueError(f"No columns parsed for {table_name}")
    if primary_key is None:
        raise ValueError(f"No primary key parsed for {table_name}")
    return {
        "table": table_name,
        "columns": columns,
        "primary_key": primary_key,
        "indexes": indexes,
    }


def mysql_unescape(value: str) -> str | None:
    if value == r"\N":
        return None
    mapping = {
        "0": "\0",
        "b": "\b",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "Z": "\x1a",
        "\\": "\\",
        "'": "'",
        '"': '"',
    }
    result = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            escaped = value[index + 1]
            result.append(mapping.get(escaped, escaped))
            index += 2
        else:
            result.append(char)
            index += 1
    return "".join(result)


def convert_value(value: str | None, column_type: str):
    if value is None:
        return None
    if column_type == "INTEGER" and value != "":
        return int(value)
    if column_type == "REAL" and value != "":
        return float(value)
    return value


def iter_rows(raw_data: bytes, schema: dict):
    text = raw_data.decode("cp1252")
    expected_columns = len(schema["columns"])
    types = [column["sqlite_type"] for column in schema["columns"]]
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != expected_columns:
            raise ValueError(
                f"{schema['table']}.txt line {line_number}: expected "
                f"{expected_columns} fields, found {len(fields)}"
            )
        yield tuple(
            convert_value(mysql_unescape(value), column_type)
            for value, column_type in zip(fields, types, strict=False)
        )


def create_table(connection: sqlite3.Connection, schema: dict) -> None:
    definitions = []
    for column in schema["columns"]:
        definition = (
            f"{quote_identifier(column['name'])} {column['sqlite_type']}"
        )
        if column["name"] == schema["primary_key"]:
            definition += " PRIMARY KEY"
        definitions.append(definition)
    connection.execute(
        f"CREATE TABLE {quote_identifier(schema['table'])} "
        f"({', '.join(definitions)})"
    )


def create_indexes(connection: sqlite3.Connection, schema: dict) -> None:
    for index in schema["indexes"]:
        index_name = f"idx_{schema['table']}_{index['name']}"
        columns = ", ".join(quote_identifier(value) for value in index["columns"])
        connection.execute(
            f"CREATE INDEX {quote_identifier(index_name)} "
            f"ON {quote_identifier(schema['table'])} ({columns})"
        )


def insert_table(
    connection: sqlite3.Connection, schema: dict, raw_data: bytes
) -> int:
    column_names = [column["name"] for column in schema["columns"]]
    placeholders = ", ".join("?" for _ in column_names)
    quoted_columns = ", ".join(quote_identifier(value) for value in column_names)
    statement = (
        f"INSERT INTO {quote_identifier(schema['table'])} "  # noqa: S608
        f"({quoted_columns}) VALUES ({placeholders})"  # Identifiers are checksum-pinned.
    )
    count = 0
    batch = []
    for row in iter_rows(raw_data, schema):
        batch.append(row)
        if len(batch) >= BATCH_SIZE:
            connection.executemany(statement, batch)
            count += len(batch)
            batch.clear()
    if batch:
        connection.executemany(statement, batch)
        count += len(batch)
    return count


def target_counts(connection: sqlite3.Connection) -> dict:
    rows = connection.execute(
        """
        SELECT m.name_metal, COUNT(*)
        FROM verkn_ligand_metal AS v
        JOIN metal AS m ON m.metalID = v.metalNr
        JOIN constanttyp AS c ON c.constanttypID = v.constanttypNr
        WHERE c.name_constanttyp = 'K'
          AND m.name_metal IN (
            'Ni<sup>2+</sup>', 'Ni<sup>3+</sup>',
            'Mn<sup>2+</sup>', 'Mn<sup>3+</sup>', 'Mn<sup>4+</sup>',
            'Co<sup>2+</sup>', 'Co<sup>3+</sup>'
          )
        GROUP BY m.name_metal
        ORDER BY m.name_metal
        """
    ).fetchall()
    return dict(rows)


def app_compatibility_check(connection: sqlite3.Connection) -> dict:
    query = """
        SELECT met.name_metal AS 'Metal ion',
               lig.name_ligand AS 'Ligand',
               lig.formula AS 'Formula',
               ligand_class.name_ligandclass AS 'Ligand class',
               beta.name_beta_definition AS 'Equilibrium',
               temperature AS 'Temperature (C)',
               ionicstrength AS 'Ionic strength',
               CASE
                 WHEN constanttyp.name_constanttyp = 'K' THEN 'Log K'
                 WHEN constanttyp.name_constanttyp = 'H' THEN 'DH (kJ/mol)'
                 WHEN constanttyp.name_constanttyp = 'S' THEN 'DS (J/mol.K)'
               END AS 'Value type',
               constant AS 'Value',
               footnote.name_footnote AS 'Note'
        FROM verkn_ligand_metal AS vlm
        LEFT JOIN liganden AS lig ON vlm.ligandenNr = lig.ligandenID
        LEFT JOIN metal AS met ON vlm.metalNr = met.metalID
        LEFT JOIN beta_definition AS beta
          ON vlm.beta_definitionNr = beta.beta_definitionID
        LEFT JOIN constanttyp ON vlm.constanttypNr = constanttyp.constanttypID
        LEFT JOIN footnote ON vlm.footnoteNr = footnote.footnoteID
        LEFT JOIN ligand_class ON lig.ligand_classNr = ligand_class.ligand_classID
        WHERE met.name_metal = 'Ni<sup>2+</sup>'
          AND constanttyp.name_constanttyp = 'K'
        LIMIT 5
    """
    cursor = connection.execute(query)
    rows = cursor.fetchall()
    return {
        "passed": len(rows) == 5 and len(cursor.description) == 10,
        "sample_rows": len(rows),
        "result_columns": [item[0] for item in cursor.description],
    }


def source_relationship_audit(connection: sqlite3.Connection) -> dict:
    checks = {
        "verkn_ligand_metal_missing_ligand": """
            SELECT COUNT(*)
            FROM verkn_ligand_metal AS v
            LEFT JOIN liganden AS l ON l.ligandenID = v.ligandenNr
            WHERE l.ligandenID IS NULL
        """,
        "verkn_ligand_metal_missing_metal": """
            SELECT COUNT(*)
            FROM verkn_ligand_metal AS v
            LEFT JOIN metal AS m ON m.metalID = v.metalNr
            WHERE m.metalID IS NULL
        """,
        "verkn_ligand_metal_missing_beta_definition": """
            SELECT COUNT(*)
            FROM verkn_ligand_metal AS v
            LEFT JOIN beta_definition AS b
              ON b.beta_definitionID = v.beta_definitionNr
            WHERE v.beta_definitionNr NOT IN (0)
              AND b.beta_definitionID IS NULL
        """,
        "literature_link_missing_ligand": """
            SELECT COUNT(*)
            FROM verkn_ligand_metal_literature AS v
            LEFT JOIN liganden AS l ON l.ligandenID = v.ligandenNr
            WHERE l.ligandenID IS NULL
        """,
        "literature_link_missing_metal": """
            SELECT COUNT(*)
            FROM verkn_ligand_metal_literature AS v
            LEFT JOIN metal AS m ON m.metalID = v.metalNr
            WHERE m.metalID IS NULL
        """,
        "literature_link_missing_literature_alt": """
            SELECT COUNT(*)
            FROM verkn_ligand_metal_literature AS v
            LEFT JOIN literature_alt AS l
              ON l.literature_altID = v.literature_altNr
            WHERE v.literature_altNr NOT IN (0)
              AND l.literature_altID IS NULL
        """,
    }
    return {
        name: connection.execute(statement).fetchone()[0]
        for name, statement in checks.items()
    }


def replacement_character_count(connection: sqlite3.Connection) -> int:
    fields = (
        ("footnote", "name_footnote"),
        ("liganden", "name_ligand"),
        ("literature_alt", "literature_alt"),
    )
    return sum(
        connection.execute(
            f"SELECT COUNT(*) FROM {quote_identifier(table)} "  # noqa: S608
            f"WHERE {quote_identifier(column)} LIKE ?",
            ("%\ufffd%",),
        ).fetchone()[0]
        for table, column in fields
    )


def build_database(source: Path, output: Path, report_path: Path, force: bool) -> dict:
    require_distinct_paths(source=source, output=output, report=report_path)
    archive_hash = sha256_file(source)
    if archive_hash != EXPECTED_ARCHIVE_SHA256:
        raise ValueError(
            "Archive SHA-256 does not match NIST's published checksum: "
            f"{archive_hash}"
        )
    if output.exists() and not force:
        raise FileExistsError(f"Output already exists: {output}; pass --force to rebuild")

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=output.stem + ".", suffix=".tmp.db", dir=output.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)

    table_report = {}
    member_report = {}
    try:
        with zipfile.ZipFile(source) as archive, closing(
            sqlite3.connect(temporary_path)
        ) as connection:
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"Corrupt ZIP member: {bad_member}")

            sql_members = sorted(
                name for name in archive.namelist() if name.endswith(".sql")
            )
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("BEGIN")

            schemas = []
            for sql_member in sql_members:
                sql_data = archive.read(sql_member)
                schema = parse_mysql_schema(sql_data.decode("ascii", errors="replace"))
                txt_member = f"{schema['table']}.txt"
                if txt_member not in archive.namelist():
                    raise ValueError(f"Missing data member: {txt_member}")
                raw_data = archive.read(txt_member)
                create_table(connection, schema)
                row_count = insert_table(connection, schema, raw_data)
                schemas.append(schema)
                table_report[schema["table"]] = {
                    "rows": row_count,
                    "columns": len(schema["columns"]),
                    "primary_key": schema["primary_key"],
                }
                member_report[sql_member] = {
                    "bytes": len(sql_data),
                    "sha256": sha256_bytes(sql_data),
                }
                member_report[txt_member] = {
                    "bytes": len(raw_data),
                    "sha256": sha256_bytes(raw_data),
                    "non_ascii_bytes": sum(value >= 128 for value in raw_data),
                }

            for schema in schemas:
                create_indexes(connection, schema)

            connection.execute(
                """
                CREATE TABLE _build_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            built_at = datetime.now(UTC).isoformat()
            metadata = {
                "builder_version": BUILDER_VERSION,
                "built_at_utc": built_at,
                "source_filename": source.name,
                "source_sha256": archive_hash,
                "source_text_encoding": "Windows-1252 (MySQL latin1-compatible)",
                "source_notice": (
                    "Built from NIST SRD 46 SQL.zip; source SQL extraction is "
                    "third-party and NIST provides it AS IS. Derived distributions "
                    "must acknowledge NIST and state the date and nature of changes; "
                    "see DATA_NOTICE.md."
                ),
            }
            connection.executemany(
                "INSERT INTO _build_metadata (key, value) VALUES (?, ?)",
                metadata.items(),
            )
            connection.commit()
            connection.execute("ANALYZE")
            connection.execute("VACUUM")

            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            counts = target_counts(connection)
            compatibility = app_compatibility_check(connection)
            relationship_audit = source_relationship_audit(connection)
            replacement_characters = replacement_character_count(connection)
            warnings = [
                f"{name}: {count} unresolved source relationship(s)"
                for name, count in relationship_audit.items()
                if count
            ]
            if replacement_characters:
                warnings.append(
                    f"decoded text contains {replacement_characters} replacement character(s)"
                )
            if integrity != "ok":
                raise ValueError(f"Built SQLite database failed integrity check: {integrity}")
            if not compatibility["passed"]:
                raise ValueError("Built SQLite database failed the application query check")
            report = {
                "builder_version": BUILDER_VERSION,
                "built_at_utc": built_at,
                "source": {
                    "path": portable_report_path(source),
                    "sha256": archive_hash,
                    "checksum_matches_nist": True,
                    "text_encoding": "cp1252",
                },
                "output": {
                    "path": portable_report_path(output),
                    "size_bytes": temporary_path.stat().st_size,
                },
                "validation": {
                    "zip_integrity": "ok",
                    "sqlite_integrity": integrity,
                    "tables_imported": len(table_report),
                    "source_rows_imported": sum(
                        item["rows"] for item in table_report.values()
                    ),
                    "app_query_compatibility": compatibility,
                    "target_log_k_counts": counts,
                    "replacement_character_count": replacement_characters,
                    "source_relationship_audit": relationship_audit,
                    "source_quality_warnings": warnings,
                },
                "tables": table_report,
                "archive_members": member_report,
            }

        temporary_path.replace(output)
        report["output"]["sha256"] = sha256_file(output)
        report["output"]["size_bytes"] = output.stat().st_size
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return report
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="SRD 46 SQL.zip")
    parser.add_argument("--output", required=True, type=Path, help="Output SQLite DB")
    parser.add_argument("--report", required=True, type=Path, help="Build report JSON")
    parser.add_argument("--force", action="store_true", help="Replace an existing output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_database(args.source, args.output, args.report, args.force)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Built: {report['output']['path']}")
    print(f"SHA-256: {report['output']['sha256']}")
    print(
        "Imported: "
        f"{report['validation']['tables_imported']} source tables, "
        f"{report['validation']['source_rows_imported']:,} rows"
    )
    print(f"SQLite integrity: {report['validation']['sqlite_integrity']}")
    print(
        "Existing App query compatibility: "
        f"{report['validation']['app_query_compatibility']['passed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
