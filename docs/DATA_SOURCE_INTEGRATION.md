# Adding Future Data Sources

## Core rule

Do not import a new source directly into `NIST_SRD_46_rebuilt.db`. That file is an
immutable, reproducible staging representation of one source. Every additional
source, including a converted local Excel workbook, must enter through its own
adapter and staging area.

The application should eventually query a separate curated database or unified
read-only view:

```text
NIST SRD 46 archive ──> NIST adapter ──> NIST staging DB ──┐
                                                          │
Verified Excel copy ──> Excel adapter ──> Excel staging DB ├─> validation/review
                                                          │          │
Other source ────────> source adapter ──> source staging ──┘          v
                                                        curated database
                                                                 │
                                                active-record read-only view
                                                   ├─> Streamlit app
                                                   ├─> API
                                                   └─> versioned ML exports
```

## Recommended source layout

Each source receives a stable `source_id` and a separate directory:

```text
data/sources/<source_id>/
├── raw/                 # immutable original or verified copy
├── staging/             # source-shaped SQLite or Parquet output
├── reports/             # checksums, row counts, validation results
└── source.yaml          # identity, version, license, and adapter configuration

ingestion/
├── adapters/
│   ├── nist_srd46.py
│   └── verified_excel.py
├── canonical_schema.sql
├── validate.py
└── promote.py
```

Raw files and generated staging databases should remain excluded from Git. Import
code, schemas, source configuration templates, and validation reports can be tracked.

## Adapter contract

Every source adapter should perform the same stages:

1. Verify the input checksum and source identity.
2. Read a copy of the source without modifying the original.
3. Preserve source row IDs, sheet names, and raw values.
4. Map source columns into a common candidate-record schema.
5. Parse numeric values into separate normalized fields.
6. Validate required identities, conditions, references, and units.
7. Write a source-specific staging output.
8. Produce a machine-readable validation report.
9. Require explicit review before promotion to the curated database.

An Excel adapter should never write back to the input workbook. It should read a
frozen, checksummed copy and record the workbook file name, sheet name, and original
row number for every imported candidate.

## Minimum canonical provenance

Each candidate constant should contain at least:

- `record_id`: stable canonical record identifier
- `source_id`: source registry identifier
- `source_version`: checksum or released source version
- `source_record_id`: original source key or Excel row locator
- `ligand_id`: reviewed canonical ligand identifier
- `metal_species_id`: reviewed canonical metal-species identifier
- `reaction_type`: equilibrium and stoichiometry
- `value_type`: K, H, S, or another explicitly defined type
- `reported_value_text`: unchanged source representation
- `numeric_value`: parsed numeric value when valid
- `temperature_raw` and `temperature_k`
- `ionic_strength_raw` and normalized ionic strength when valid
- `solvent`, `electrolyte`, pH, measurement method, model, and uncertainty
- `reference_id`: verified record-level source when available
- `verification_status`: candidate, reviewed, verified, rejected, or superseded
- `quality_flags`: structured validation findings
- `supersedes_record_id`: prior record replaced by a verified correction
- `is_active`: whether the record appears in the default curated view

## Conflict and replacement policy

Do not overwrite a NIST or earlier record in place.

- Exact duplicate with the same conditions: link it as corroborating provenance or
  mark it as a duplicate after review.
- Same ligand and metal but different conditions or stoichiometry: retain both.
- New primary literature corrects an old value: add a new record, set
  `supersedes_record_id`, and mark the old record as superseded.
- Unresolvable disagreement: retain both with a conflict quality flag.
- Missing exact provenance: keep the record as a candidate; do not promote it to
  verified status.

The default application view should query only active records, while a history view
should expose superseded values and the reason for each decision.

## Safe Excel ingestion sequence

When a verified local workbook is ready:

1. Copy it into a new source-specific `raw/` directory.
2. Calculate and record its SHA-256 checksum.
3. Register it with a unique `source_id` and version.
4. Inspect sheet names, headers, IDs, data types, and formulas.
5. Map fields explicitly; do not infer missing identities or conditions.
6. Import into a source-specific staging database.
7. Run referential, chemical-identity, unit, range, and provenance checks.
8. Review the validation report.
9. Promote approved rows into the curated database as new versioned records.
10. Publish a new dataset release for the app or machine-learning pipeline.

## Machine-learning boundary

Machine-learning code must not train directly from a mutable application table. A
dataset builder should select a specific curated release, freeze its record IDs and
features, write a manifest and checksum, and then export CSV or Parquet. Predictions
belong in separate model-output tables and must never overwrite experimental values.

## Recommended next implementation

The canonical schema, source registry, adapter interface, NIST adapter, validation
report, candidate release, canonical app queries, offline review-decision template,
review-to-curated generator, and verified-only machine-learning publication gate are
implemented. The next data-source step is an Excel adapter built against a frozen copy
of a workbook, without connecting it directly to the live application database.
