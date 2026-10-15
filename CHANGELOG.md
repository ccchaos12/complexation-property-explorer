# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project intends to use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No unreleased changes.

## [0.4.1] - 2026-10-15

### Fixed

- Compare solvent and electrolyte metadata when classifying strict duplicates;
  restore 15 previously hidden Supplement records in the full local dataset.
- Reject empty, null and placeholder molecular structure arrays as identity evidence.
- Count distinct hidden records separately from duplicate relationships, allowing
  one Supplement record to match multiple NIST records without failing a build.
- Keep active duplicates visible when their preferred records are rejected or
  superseded; only suppress publication records when a preferred record also
  satisfies all publication requirements.
- Display exact record-level references separately from pair-level candidates and
  preserve exact citations and provenance granularity in filtered CSV exports.
- Reject floating-point overflow instead of importing infinite numeric constants.

- Replace raw citation-use flags with readable source-status labels; keep `0`
  distinct from proof of use or verification, report conflicting/missing/unknown
  flags, and group repeated links into one citation per source reference ID.
- Preserve original reference flags in an explained, collapsed metadata table;
  retain valid negative log K values unchanged.

### Security

- Upgrade GitPython to 3.1.62, Tornado to 6.5.9 and urllib3 to 2.8.0,
  covering the patched versions identified by the repository's open Dependabot alerts.

### Changed

- Replace reference tables with searchable citation cards, separating direct record
  links from related literature. Keep source identifiers and original flags in
  per-citation details; show exceptional source statuses beside the citation.
- Add individual/all-match citation copying and bibliography CSV export with
  provenance. Load related citations ten at a time while copying/exporting all
  matches; offer source links only for explicit URLs or DOIs in the citation.
- Use canonical schema 3 so launchers preserve and rebuild old generated databases.
  Custom curated databases require rebuilding their base and replaying saved reviews.
- Add portable regression coverage for identity, deduplication, publication,
  provenance and schema compatibility. See `docs/DEBUG_AUDIT_20261015.md`.

## [0.4.0] - 2026-07-20

### Added

- Add a source-scoped adapter for the immutable local Excel supplement.
- Build one unified NIST-plus-supplement canonical SQLite with stable
  `SUPPLEMENT:*` IDs and exact Supplement record-to-reference links.
- Record cross-source structure, formula, and strict constant-duplicate screening
  counts in the canonical build report.
- Add canonical schema version 2 relationship tables for 50 exact-structure ligand
  links and 15 strict cross-source constant duplicate links.
- Show duplicate and ligand-identity context in record details, with a search option
  to include retained duplicate source records.

### Changed

- Apply the project owner's all-verified application policy to the unified local
  database while retaining the policy basis in the release manifest.
- Reuse canonical NIST metal identities for Supplement records to avoid duplicate
  metal filters.
- Hide the duplicate side of strict cross-source matches from searches and
  verified-only publication by default while retaining both verified source records.

## [0.3.0] - 2026-07-17

### Added

- Add a one-click Windows entry point that prepares and starts the app.
- Download the original NIST SRD 46 SQL archive and accompanying README directly
  from NIST on first launch.
- Verify official source files against their published SHA-256 checksums before use.
- Wait for the local Streamlit health endpoint and open the default browser
  automatically on Windows, macOS, and Linux.

### Changed

- Make `run.sh` and `run.command` complete first-time environment and database
  preparation instead of requiring a prebuilt database.
- Rewrite first-time setup documentation around one launcher per platform.
- Upgrade Streamlit to 1.54.0 and PyArrow to 23.0.1 to include published security
  fixes.

### Fixed

- Validate the staging and canonical SQLite databases before reuse, preserve invalid
  generated files, and rebuild them automatically.
- Reject damaged or incompatible custom databases with a readable recovery message.
- Encode SQLite file URIs correctly when paths contain reserved characters.
- Select the next available local port instead of opening an unrelated service on
  port 8501, and reliably clean up failed child processes.
- Preserve direct script execution as well as module-based database preparation.
- Prevent source, database, report, and publication output path collisions.
- Roll back both publication outputs if installation of either the CSV or manifest
  fails.

## [0.2.0] - 2026-07-16

### Added

- MIT License for the new Python application code.
- Python and Streamlit read-only research interface.
- Reproducible SRD 46 to SQLite conversion and canonical schema.
- All-metal search, numeric and reaction filters, pagination, record selection,
  comparison, reference browsing, and CSV export.
- Unicode display formatting for formulae and equilibrium expressions.
- Source-aware Record IDs and dataset build/checksum metadata.
- Offline curation and explicit publication boundaries.
- Portable two-source tests, continuous integration, and local launchers.

### Changed

- Replaced the legacy Windows/Pascal application route with the maintained Python app.
- Redesigned the interface as a compact coordination-chemistry workbench.
- Removed verification controls from the public research interface.

### Removed

- Legacy executable, DLL, Pascal source, bundled database, presentation assets, and
  hidden review page from the distributable project package.
