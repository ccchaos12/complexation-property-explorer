# v0.4.1 scientific-integrity audit — October 15, 2026

This audit starts from `6237393` on `main` (v0.4.0). It focuses on the path from
immutable staging sources to identity matching, search, exact citations and
verified-only publication. It does not reverify literature values or modify the
project's Excel workbook. The owner's existing application verification policy
remains unchanged.

## Confirmed defects and corrections

| Defect | Reproduction / impact | Correction |
|---|---|---|
| Medium omitted from strict matching | All 15 previously hidden Supplement records have different or missing solvent/electrolyte metadata relative to their preferred NIST records. | Compare both raw fields before classifying a strict duplicate. No automatic normalization or inferred solvent. |
| Missing structures treated as identities | Equal `[]`, `[null]`, empty strings or placeholder arrays can produce identity and duplicate links. The full NIST source has 1,329 empty structure arrays. | Require a nonempty JSON array of non-placeholder encoded structures. |
| Relationship count confused with hidden-record count | One local record matching two NIST records creates two relationships but hides one record, causing a valid build to fail. | Validate and report distinct duplicate record IDs separately from relationship counts. |
| Inactive preferred record still suppresses an active record | Rejecting or superseding the preferred record leaves the active duplicate absent from searches and summaries. | Only an active preferred record can suppress a duplicate in the canonical view and queries. |
| Publication loses eligible local records | A verified local record with an exact verified citation is suppressed by a NIST record lacking an exact citation; neither is exported. | Suppress only when the preferred record independently meets every publication criterion. Record this rule in the publication manifest. |
| Exact citations absent from UI and CSV | The supplement contains 281 exact reference links, but the UI only queries ligand/metal candidate links. | Show the exact citation separately and include its ID, code, text and provenance granularity in extended results and CSV. |
| Numeric overflow enters scientific data | `strict_float('1e999')` returns infinity despite the strict-number pattern. | Accept only finite parsed floats and retain the original reported text. |

Example of the first defect: `SUPPLEMENT:CONSTANT:188` was linked to
`NIST_SRD46:CONSTANT:102025`. The Supplement solvent is missing and its electrolyte
text is `I=0.1 M KNO3`; the NIST solvent is `H<sub>2</sub>O` and its electrolyte is
missing. Matching value, temperature and ionic strength cannot establish an exact
medium match. The correction retains both rows without asserting they represent
different experiments or claiming the underlying measurements are incorrect.

## Dependency security fixes

GitHub reports open alerts for the runtime's locked GitPython, Tornado and urllib3
versions, including a critical GitPython configuration-injection advisory. Updated
only these three dependency pins: GitPython 3.1.52 → 3.1.62, Tornado 6.5.7 → 6.5.9,
and urllib3 2.7.0 → 2.8.0. These reach the patched versions reported in the open
alerts and match the corresponding Dependabot patch proposals.

Examples of upstream advisories:
[GitPython](https://github.com/gitpython-developers/GitPython/security/advisories/GHSA-284h-m62q-gf8w),
[Tornado](https://github.com/tornadoweb/tornado/security/advisories/GHSA-c2m8-h5v5-343r),
[urllib3](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw).
Installed the complete updated lockfile in an isolated environment; `pip check`
passes and the full 72-test suite passes there as well. This does not assert that
all application paths are exploitable or that every possible vulnerability has
been excluded. Alerts against the default branch can remain open until merge.

## Full-data validation

Rebuilt both the NIST-only and unified databases from the existing immutable
staging files. Input checksums are recorded in `data/reports/`.

| Unified measure | v0.4.0 | v0.4.1 |
|---|---:|---:|
| Source records retained | 90,105 | 90,105 |
| Records visible by default | 90,090 | 90,105 |
| log K records visible by default | 60,756 | 60,771 |
| Strict duplicate relationships | 15 | 0 |
| Exact structure relationships | 50 | 50 |
| Supplement exact reference links | 281 | 281 |

Both builds pass SQLite integrity and foreign-key validation. Source values,
source IDs and exact reference links are preserved. Zero strict duplicate matches
means none satisfy the implemented exact-match criteria; it is not proof that the
literature contains no duplicates.

## Verification

- Full local suite: **72 tests pass, no skips**, including the complete databases.
- Twelve new portable regression tests exercise production SQL, build validation,
  schema upgrade, numeric parsing and Streamlit rendering/CSV export. Only the
  source-adapter boundary is mocked for the small unified-build fixtures.
- Running these tests against unmodified `6237393` produces 19 failed assertions
  (including parameterized subcases) and two errors; the corrected branch passes.
- Ruff 0.12.0, Python compilation, Unix launcher syntax and Git whitespace checks pass.
- Real Chrome with the full unified database: initial 60,771 log K results,
  next/first-page navigation, ligand filtering and CSV preparation succeed.
  Browser checks at 1440, 768 and 320 pixels report no JavaScript page errors;
  768- and 320-pixel layouts have no document-level horizontal overflow.
- Windows launcher behavior is covered by the existing Windows CI job; it was not
  executed locally on macOS.

## Upgrade and compatibility

Schema 3 is required because an old database retains the previous relationship
classification and view definitions even after Python code is upgraded. The normal
launcher preserves an old default generated database under an
`*.invalid-<timestamp>.db` filename and rebuilds it from staging. Regression tests
verify that the backup bytes are unchanged and the rebuilt database is compatible.

For a custom `COMPLEXATION_DB_PATH`, the app, publication and curation entry points
reject schema 2 with a rebuild explanation. They never replace the custom file.
Rebuild its base with `ingestion.build_canonical` or `ingestion.build_unified`, then
reapply the saved review-decision CSV files in their original order to separate
curated outputs. Keep the original curated file and decisions until validation is
complete. Do not merely change `PRAGMA user_version`; that would retain incorrect
relationships and view behavior.

Filtered CSV now includes exact-reference columns and calls the pair-level count
`Candidate references`. Consumers depending on column names should update their
mappings. The v0.4.0 Word manual remains a historical manual; this note documents
the changed behavior.

## Follow-up: misleading reference flags

The candidate-reference table previously displayed raw `not_used_flag` integers.
The immutable local build contains 36,699 links with `-1` and 43,460 with `0`.
No reference code or citation text is a standalone `-1`; the misleading display
comes from the flag column. Twenty-four ligand/metal/reference groups contain both
flag values, so selecting one link's value would silently discard a conflict.

The app now interprets the legacy Boolean convention for the field `not_used`:
`-1` (and `1`) means the flag is set, displayed as **Flagged as not used**; `0`
is **Not flagged as unused**, deliberately not "used", "verified" or "reliable".
Missing and unrecognized flags have separate labels. This is a display
interpretation of the source field, not a new review of the paper. The
[NIST manual](https://www.nist.gov/system/files/documents/srd/46_8.htm) describes
pair-level bibliographies and retention of references whose constants were not
selected, but does not document this third-party SQL flag's numeric encoding.

The default table has one citation per source reference ID and flags contradictory
links as **Conflicting source flags**. Distinct comments are retained. Original
flag values remain available in the collapsed **Source reference metadata** table,
with the interpretation explained alongside them; the query API and SQLite are
unchanged. No general replacement of negative numbers is performed.

Six new regressions cover flags, conflicts, missing metadata, repeated links,
separate source IDs and the live Streamlit table. A valid log K of `-1` remains
`-1` in results and CSV, and the database remains byte-for-byte unchanged. The
full follow-up suite passes **78 tests with no skips**.
