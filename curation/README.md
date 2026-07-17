# Review and Promotion Workflow

The canonical candidate database is immutable. Review decisions are recorded in a
CSV file and applied to a new curated database copy.

## Decision file

Copy `review_decisions.template.csv` and keep the exact English header order:

```text
review_id,record_id,decision,reviewer,reviewed_at_utc,reason,verified_reference_id,supersedes_record_id
```

Allowed decisions:

- `reviewed`: identity and conditions were reviewed, but exact provenance may remain incomplete.
- `verified`: requires an exact `verified_reference_id` from `source_references`.
- `rejected`: removes the record from the active view in the curated output.

Only a `verified` decision may specify `supersedes_record_id`. The superseded record
is retained in history and marked inactive. A verified reference must already belong
to the record's ligand-metal candidate-reference set. Supersession is allowed only
when ligand, metal species, and value type match.

The decision CSV is the complete review input for each generated curated database.
Retain reviewed decision files as immutable, checksummed audit artifacts outside the
generated database directory.

## Generate a curated database

```bash
python3 -m curation.apply_reviews \
  --canonical "data/generated/stability_constants_canonical.db" \
  --decisions "curation/review_decisions.csv" \
  --output "data/generated/stability_constants_curated.db" \
  --report "data/reports/curation_report.json"
```

The command validates all record IDs, references, timestamps, decisions, and
supersession links. It refuses to overwrite an existing output unless `--force` is
provided. Review events are append-only in the generated curated database.

The resulting reviewed release is not automatically approved for machine learning.
Training approval requires a separate dataset publication policy and release step.
