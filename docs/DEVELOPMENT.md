# Development Guide

## Local workflow

Create a branch for each focused change and keep generated data outside Git:

```bash
git switch -c feature/short-description
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run the application with `./run.sh`; the launcher prepares the canonical database
when it is missing. To test a different database, set `COMPLEXATION_DB_PATH` to its
absolute path.

## Architecture

- `app.py` composes the Streamlit interface and session state.
- `complexation_explorer/database.py` contains parameterized, read-only SQLite queries.
- `complexation_explorer/formatting.py` converts source markup for display only.
- `complexation_explorer/ui.py` contains reusable presentation and layout helpers.
- `ingestion/` converts source-specific staging data into the canonical schema.
- `curation/` applies explicit review decisions to a separate database.
- `publication/` freezes approved records into versioned dataset releases.

The public app queries `active_constant_records`. Review, promotion, and publication
remain offline operations so a browser session cannot change scientific data.

## Data invariants

- Raw archives are immutable.
- Reproducible staging databases are rebuilt, not hand-edited.
- Source text and parsed values remain separate.
- Different temperatures, solvents, ionic strengths, and stoichiometries remain
  distinct records.
- Every imported record retains source version, checksum, and original identifier.
- Literature candidates are not presented as exact record-level provenance unless the
  source supports that relationship.
- Corrected data is added with provenance; historical source records are not silently
  overwritten.

Read [`DATA_SOURCE_INTEGRATION.md`](DATA_SOURCE_INTEGRATION.md) before implementing a
new adapter.

## Canonical build

The standard preparation entry point downloads and verifies the official source when
it is missing, then builds both database layers:

```bash
python -m scripts.prepare_app
```

For an explicit manual rebuild:

```bash
python scripts/build_srd46_sqlite.py \
  --source "data/raw/SRD 46 SQL.zip" \
  --output "data/generated/NIST_SRD_46_rebuilt.db" \
  --report "data/reports/srd46_build_report.json"

python -m ingestion.build_canonical \
  --staging "data/generated/NIST_SRD_46_rebuilt.db" \
  --output "data/generated/stability_constants_canonical.db" \
  --report "data/reports/canonical_build_report.json"
```

Use `--force` only for an intentional rebuild of a generated output.

## Verification

Before opening a pull request:

```bash
python -m unittest discover -s tests -v
python -m ruff check app.py complexation_explorer ingestion curation publication scripts tests
python -m compileall -q app.py complexation_explorer ingestion curation publication scripts tests
bash -n run.sh run.command
```

Also start the app and check the compact result table, pagination, row-to-detail
selection, comparison search, reference limitation notice, CSV preparation, sidebar
collapse, and layouts at 320, 768, and desktop widths.
