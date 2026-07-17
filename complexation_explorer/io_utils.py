"""Shared safeguards for local paths and read-only SQLite connections."""

from __future__ import annotations

from pathlib import Path


def readonly_sqlite_uri(path: str | Path) -> str:
    """Return an encoded SQLite URI that cannot confuse path characters with options."""
    resolved = Path(path).expanduser().resolve()
    return f"{resolved.as_uri()}?mode=ro"


def require_distinct_paths(**paths: Path) -> None:
    """Reject path aliases that could overwrite an input or a second output."""
    resolved_paths: dict[Path, list[str]] = {}
    for label, path in paths.items():
        resolved_paths.setdefault(path.expanduser().resolve(), []).append(label)

    collisions = [
        f"{', '.join(labels)} -> {path}"
        for path, labels in resolved_paths.items()
        if len(labels) > 1
    ]
    if collisions:
        raise ValueError("Paths must be distinct: " + "; ".join(collisions))
