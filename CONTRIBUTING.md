# Contributing

Contributions are welcome under the project's MIT License.

## Before proposing a change

- Open an issue for substantial architecture or schema changes.
- Keep one pull request focused on one problem.
- Do not commit raw source archives, generated databases, private workbooks, local
  environments, credentials, or personal paths.
- Do not change source scientific values to improve appearance or make datasets agree.

## Development checks

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m ruff check app.py complexation_explorer ingestion curation publication scripts tests
python -m compileall -q app.py complexation_explorer ingestion curation publication scripts tests
bash -n run.sh run.command
```

For interface changes, also test the live app at 320, 768, and desktop widths. Confirm
that controls remain readable, keyboard focus is visible, the page has no horizontal
overflow, and row selection still updates record details.

## Scientific-data changes

A data contribution must include:

- source identity, version, and checksum;
- original row or record identifier;
- unchanged reported value and units;
- temperature, ionic strength, solvent, electrolyte, and stoichiometry when reported;
- literature metadata and provenance granularity;
- validation results and an explicit review decision.

Never overwrite an older source record in place. Add a traceable correction or
superseding record through the curation workflow.

## Pull requests

Describe the user-facing outcome, data impact, verification performed, and any release
or migration implications. Update documentation and tests with behavior changes.
