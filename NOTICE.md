# Notices and Attribution

## Application lineage

This repository contains a Python and Streamlit rewrite of the Stability Constant
Explorer originally created by Naoyuki Hatada, Ph.D. The upstream project is
available at <https://github.com/n-hatada/stability-constant-explorer> and described
its original source code and executable as released into the public domain.

The rewrite changes the application architecture, database schema, build pipeline,
query layer, user interface, tests, and release workflow. It does not imply endorsement
by the upstream author.

## NIST SRD 46

The initial data source should be cited as:

Donald R. Burgess (2004), *NIST SRD 46. Critically Selected Stability Constants of
Metal Complexes: Version 8.0 for Windows*, National Institute of Standards and
Technology, <https://doi.org/10.18434/M32154> (accessed July 16, 2026).

The generated canonical SQLite database is a modified derivative of the downloaded
source package. The conversion stores source values separately from parsed fields,
adds source-scoped identifiers and metadata, and records build checksums and reports.
The complete dated modification statement, data-quality warning, reuse conditions,
and distribution policy are in [`DATA_NOTICE.md`](DATA_NOTICE.md). Include that file
with any distribution of NIST-derived data.

## Third-party software

SQLite is in the public domain. Python dependencies retain their own licenses; consult
the installed packages and their upstream projects for the applicable terms.

## Project code license

The new Python application code is licensed under the MIT License, copyright 2026
ccchaos12 (Kexin Chen). See `LICENSE` for the complete terms. This license applies to
the new application code and documentation; it does not replace the separate notices
and terms that apply to NIST-derived data, SQLite, dependencies, or upstream
public-domain material.
