# Verified-Only Dataset Publication

This publication gate creates an immutable CSV and JSON manifest for an approved
machine-learning experiment. It reads a curated SQLite database in read-only mode
and never reads the local Excel database.

## Requirements

Every exported record must be active, verified, numeric, and linked to an exact
reference whose status is also verified. Candidate, reviewed, rejected, and
superseded records are excluded. Publication fails when no eligible records exist.

## Publish a dataset

1. Copy `approval.template.json` to a separate approval file.
2. Complete every field without changing the field names or safety requirements.
3. Run:

```bash
python3 -m publication.publish_dataset \
  --database data/generated/stability_constants_curated.db \
  --approval publication/approval.json \
  --output data/published/ml_stability_constants.csv \
  --manifest data/published/ml_stability_constants.manifest.json
```

The manifest records the database, approval, and dataset SHA-256 checksums; the
selection rules; approver; purpose; record count; and publication time. Existing
outputs are protected unless `--force` is explicitly supplied.

The approval file and generated publication files should remain local unless their
contents have been reviewed for distribution and licensing. Any distributed export
derived from NIST SRD 46 must include the repository-level `DATA_NOTICE.md`. The
generated manifest records distribution metadata for every source represented in the
export. NIST entries include the DOI, data-terms URL, modification-notice path, and
the requirement to distribute that notice with the dataset; unfamiliar future
sources are marked as requiring distribution review.
