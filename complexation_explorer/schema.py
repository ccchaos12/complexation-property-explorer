"""Canonical schema compatibility shared by readers and offline workflows."""

SCHEMA_VERSION = 3
SCHEMA_VERSION_LABEL = "3.0.0"


def require_current_schema(connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported canonical schema version: {version}; expected {SCHEMA_VERSION}. "
            "Rebuild generated databases from staging with the current version. "
            "For curated databases, rebuild the base and reapply the saved review decisions."
        )
