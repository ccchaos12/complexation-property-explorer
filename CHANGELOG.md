# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project intends to use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Add future source adapters only through the documented provenance workflow.
- Add the NIST SRD 46 citation, dated derivative-work notice, and release metadata.
- Remove internal design-audit state and non-reproducible pilot-review artifacts.
- Rename the project and Python package to Complexation Property Explorer.
- Rewrite the first-time setup guide with separate Windows and macOS/Linux paths.
- Add current application screenshots and a task-oriented README.
- Restrict Streamlit to localhost and disable anonymous usage statistics.
- Add multi-version Linux and Windows CI, pinned Actions, Dependabot, and citation metadata.

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
