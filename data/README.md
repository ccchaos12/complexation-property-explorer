# SRD 46 Data Build Directory

This directory supports reproducible generation of an independent SQLite database
from the NIST `SRD 46 SQL.zip` package.

## Directory boundaries

- `raw/`: the launcher-downloaded original NIST files; read-only and excluded from
  Git.
- `generated/`: reproducible SQLite outputs; excluded from Git.
- `reports/`: build validation reports and source manifests; suitable for Git.

This process does not modify an Excel database outside the repository. When the
verified local supplement SQLite is present in `generated/`, the unified build reads
that immutable staging database without reopening or changing the original workbook.
It also does not modify the source archive in `raw/`; every application SQLite output
is rebuilt in `generated/`.

## Build

For the normal automatic download and two-layer build:

```bash
python3 -m scripts.prepare_app
```

The command downloads the original SQL archive and dataset README from NIST when
missing and verifies both published SHA-256 checksums. For an explicit staging-only
build:

```bash
python3 scripts/build_srd46_sqlite.py \
  --source "data/raw/SRD 46 SQL.zip" \
  --output "data/generated/NIST_SRD_46_rebuilt.db" \
  --report "data/reports/srd46_build_report.json"
```

Add `--force` to rebuild an existing output.

## Build the canonical candidate database

After rebuilding the NIST staging database, create the source-independent canonical
candidate layer:

```bash
python3 -m ingestion.build_canonical \
  --staging "data/generated/NIST_SRD_46_rebuilt.db" \
  --output "data/generated/stability_constants_canonical.db" \
  --report "data/reports/canonical_build_report.json"
```

The canonical output contains stable source-scoped IDs, source registry metadata,
raw and parsed value fields, verification status, structured quality flags,
candidate reference links, and a frozen exploration-only dataset release. It does
not contain verified records unless a future explicit review and promotion workflow
adds them.

## Build the unified verified application database

When the immutable local supplement is available, build the single database used by
the application:

```bash
python3 -m ingestion.build_unified \
  --nist-staging "data/generated/NIST_SRD_46_rebuilt.db" \
  --supplement-staging \
    "data/generated/Local_Excel_NIST_SRD_46_Supplement_20260719.db" \
  --output "data/generated/Complexation_Constants_Unified_rebuilt.db" \
  --report "data/reports/unified_rebuilt_build_report.json"
```

This build preserves the two staging databases, assigns
`SUPPLEMENT:*` canonical IDs, reuses canonical NIST metal identities,
and records the project owner's all-verified policy in the release manifest. It does
not create per-record review events or approve a machine-learning publication.
Canonical schema version 2 also stores exact-structure ligand identity relationships
and strict cross-source constant-duplicate relationships. Both source records remain
active; the application hides the duplicate side by default.

## Data-layer role

The generated database is a faithful staging conversion of the NIST SQL package,
not an academically verified curated database. Source table names, primary keys,
and text values are preserved. MySQL `latin1` text is decoded as Windows-1252 and
stored as SQLite UTF-8, preserving degree symbols, micro signs, and smart quotes.

SQLite includes an additional `_build_metadata` table containing the source archive
checksum, build time, text encoding, and builder version. This table does not affect
queries used by the original Stability Constant Explorer.

The build report flags unresolved relationships and other source-quality issues.
The converter reports these issues without guessing missing values or silently
changing source records.

## License and data quality

Data source: NIST SRD 46, DOI `10.18434/M32154`.

The NIST README states that the SQL package was extracted from the legacy Windows
database by a third party. NIST does not warrant its reliability and notes known
errors in the structure data. Any cleaned, corrected, or derived release must retain
NIST attribution and record the date and nature of each modification. See the
repository-level [`DATA_NOTICE.md`](../DATA_NOTICE.md) for the required citation,
dated modification statement, reuse terms, and distribution policy.
