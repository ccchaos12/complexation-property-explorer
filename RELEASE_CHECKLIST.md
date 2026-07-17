# GitHub Release Checklist

## Required before the first public release

- [x] Select a license for the new Python code and add `LICENSE`.
- [x] Document the dataset-specific NIST reuse conditions, citation, dated
      modification notice, and separate data/software license boundary in
      `DATA_NOTICE.md`.
- [x] Confirm repository owner, project URL, and GitHub issue/security-reporting paths.
- [x] Review `NOTICE.md` and the installed dependency-license metadata.

## Package hygiene

- [x] Confirm no `.db`, `.sqlite`, `.zip`, `.xlsx`, `.exe`, `.dll`, `.pptx`, `.venv`,
      cache, secret, or personal-path file is tracked.
- [x] Confirm raw data and generated databases are reproducible from documented inputs.
- [x] Inspect `git diff --check` and the complete staged-file list.
- [x] Ensure all visible text, code comments, and documentation are in English.
- [x] Prepare a clean public root commit without the upstream database, executable,
      DLL, presentation, and legacy-source history.
- [x] Disable Streamlit usage statistics and bind the local server to `127.0.0.1`.
- [x] Add software citation metadata and automated dependency-update configuration.

## Verification

- [x] Run the unit and integration test suite.
- [x] Run Ruff, Python compilation, and launcher syntax checks.
- [x] Run `PRAGMA integrity_check` and `PRAGMA foreign_key_check` on the local canonical
      database.
- [x] Test a clean CI dependency installation and portable database build.
- [x] Test Python 3.11, 3.12, and 3.13 on Linux and Python 3.13 on Windows CI.
- [x] Test the app at 320, 375, 414, 768, and desktop widths.
- [x] Verify filtering, pagination, row selection, comparison search, references, and
      CSV download.
- [ ] Smoke-test `setup_windows.bat` and `run_windows.bat` on a physical or virtual
      Windows 10/11 system.

## GitHub configuration

- [x] Add a concise repository description and relevant topics.
- [x] Enable branch protection and require the CI workflow.
- [x] Enable private vulnerability reporting.
- [x] Review issue and pull-request templates.
- [x] Pin GitHub Actions to immutable commit SHAs.
- [x] Create an annotated version tag and release notes from `CHANGELOG.md`.
