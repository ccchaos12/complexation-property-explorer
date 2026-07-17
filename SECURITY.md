# Security Policy

## Supported version

Security fixes are applied to the latest development version. No public stable release
is supported yet.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when it is enabled for the repository. Do
not place credentials, private data, unpublished datasets, or exploit details in a
public issue. If private reporting is unavailable, contact the repository owner through
the account listed on the GitHub project before sharing sensitive details.

Reports should include the affected version, reproduction steps, impact, and any safe
mitigation already tested. Acknowledgement and disclosure timing will be coordinated
after the issue is reproduced.

## Data-safety scope

The public app is intentionally read-only, listens only on `127.0.0.1`, and disables
anonymous Streamlit usage statistics. Reports that show a way to write to the
configured SQLite database, escape the selected database boundary, expose the server
beyond the local computer, disclose a local path, or include ignored raw data in a
release should be treated as security issues.
