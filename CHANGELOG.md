# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project intends to use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No unreleased changes.

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
