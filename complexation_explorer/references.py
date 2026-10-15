"""Read-only bibliography preparation, search and export helpers."""

from __future__ import annotations

import csv
import io
import re
from urllib.parse import urlsplit

from .formatting import candidate_reference_rows, display_value

DIRECT = "Direct record link"
RELATED = "Related to ligand–metal"
EXPORT_FIELDS = (
    "Record ID",
    "Reference ID",
    "Code",
    "Reference",
    "Link type",
    "Source use status",
    "Comment",
    "Source links",
)


def citation_links(citation: str) -> list[str]:
    """Link only identifiers or HTTP(S) addresses explicitly present in a citation."""
    links = []
    tokens = re.findall(r"https?://[^\s<>\"']+|\b10\.\d{4,9}/[^\s<>\"']+", citation)
    for token in tokens:
        token = token.rstrip(".,;:")
        while token.endswith(")") and token.count(")") > token.count("("):
            token = token[:-1]
        token = token.rstrip("]}")
        url = "https://doi.org/" + token if token.startswith("10.") else token
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue
            if parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        if url not in links:
            links.append(url)
    return links


def bibliography_entries(detail: dict, references: list[dict]) -> list[dict]:
    """Promote an exact citation once, retaining any pair-level flags and comments."""
    entries = candidate_reference_rows(references)
    exact_id = detail.get("verified_reference_id")
    exact = next((row for row in entries if row["Reference ID"] == exact_id), None)
    if exact_id:
        if exact is None:
            exact = {
                "Reference ID": exact_id,
                "Code": display_value(detail.get("verified_reference_code")),
                "Reference": display_value(detail.get("verified_reference")),
                "Source use status": "Not applicable — no pair-level flag",
                "Comment": "N/A",
            }
        else:
            entries.remove(exact)
        entries.insert(0, exact)
    for entry in entries:
        entry["Record ID"] = detail["record_id"]
        entry["Link type"] = DIRECT if entry["Reference ID"] == exact_id else RELATED
        entry["Source links"] = "\n".join(citation_links(entry["Reference"]))
        entry["raw_links"] = [
            dict(link) for link in references if link["reference_id"] == entry["Reference ID"]
        ]
    return entries


def filter_bibliography(entries: list[dict], query: str) -> list[dict]:
    terms = query.casefold().split()
    return [
        entry
        for entry in entries
        if all(
            term in " ".join(str(entry[field]) for field in EXPORT_FIELDS).casefold()
            for term in terms
        )
    ]


def bibliography_csv(entries: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(entries)
    return output.getvalue().encode("utf-8-sig")


def bibliography_text(entries: list[dict]) -> str:
    return "\n\n".join(entry["Reference"] for entry in entries)
