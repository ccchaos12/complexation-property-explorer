# NIST SRD 46 Data Notice

This notice applies to NIST SRD 46 source data and any database or dataset derived
from it. It does not change the MIT License that applies to this repository's new
Python application code.

## Source citation

Burgess, D. R. (2004), *NIST SRD 46. Critically Selected Stability Constants of
Metal Complexes: Version 8.0 for Windows*, National Institute of Standards and
Technology, <https://doi.org/10.18434/M32154> (accessed July 17, 2026).

## Reuse terms

The dataset record links to the [NIST copyright, fair-use, and licensing
page](https://www.nist.gov/open/license). The dataset-specific
[`SRD 46 README.txt`](https://data.nist.gov/od/ds/ark:/88434/mds2-2154/SRD%2046%20README.txt)
states that users may copy and distribute the data, improve or modify it, and create
and distribute derivative works. A modified work must:

- explicitly acknowledge the National Institute of Standards and Technology as the
  source;
- state that the data were changed; and
- state the date and nature of the changes.

Consult the authoritative
[NIST SRD 46 record](https://data.nist.gov/od/id/mds2-2154) and its attached README
before distributing a raw or derived dataset. NIST data terms apply separately from
the repository's software license.

## Modification notice for this project

Modified by ccchaos12 (Kexin Chen), July 15–17, 2026.

The project:

- converts the third-party SQL and text dump distributed by NIST into SQLite;
- decodes MySQL `latin1`-compatible source text as Windows-1252 and stores it as
  UTF-8;
- adds build metadata, checksums, integrity results, and source-quality warnings;
- maps source tables into a source-scoped canonical schema;
- stores parsed numeric, temperature, and ionic-strength fields separately from the
  unchanged reported text;
- adds quality flags and candidate reference links; and
- converts chemical markup into Unicode only for display or exported presentation,
  without overwriting source text.

These transformations do not constitute independent academic verification or a
correction of the underlying NIST values.

## Data-quality disclaimer

The dataset-specific NIST README says that SRD 46 has been discontinued and that
`SRD 46 SQL.zip` was extracted from the Windows database by a third party. NIST
cannot vouch for that extraction's reliability and notes known errors in the
structure data. NIST provides the material as is and does not endorse this project
or its transformations.

## Distribution policy for this repository

The raw NIST archive and generated databases are not tracked in Git. The launchers
download the original archive and dataset README directly from NIST, verify their
published SHA-256 checksums, and reproduce the SQLite database locally. This keeps
the standard GitHub source archive small while preserving an authoritative download
path and exact source identity.

An optional offline release bundle may redistribute the unchanged original archive
under the dataset-specific README terms only if it also includes this notice, the
NIST README, the source citation, and checksums. A transformed-data release must
additionally include a dated modification description and release manifest. Large
raw or transformed datasets belong in versioned release assets, not Git history.
