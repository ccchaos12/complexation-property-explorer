PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    publisher TEXT,
    doi TEXT,
    license_url TEXT,
    source_notes TEXT
);

CREATE TABLE source_versions (
    source_version_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    version_label TEXT NOT NULL,
    source_checksum_sha256 TEXT NOT NULL,
    staging_checksum_sha256 TEXT NOT NULL,
    ingested_at_utc TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    UNIQUE (source_id, source_checksum_sha256, staging_checksum_sha256)
);

CREATE TABLE metal_species (
    metal_species_id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(source_version_id),
    source_record_id TEXT NOT NULL,
    display_name_raw TEXT NOT NULL,
    source_code TEXT,
    species_type INTEGER,
    parent_source_record_id TEXT,
    identity_status TEXT NOT NULL DEFAULT 'source_identity',
    source_comment TEXT,
    UNIQUE (source_version_id, source_record_id)
);

CREATE TABLE ligands (
    ligand_id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(source_version_id),
    source_record_id TEXT NOT NULL,
    ligand_name_raw TEXT NOT NULL,
    formula_raw TEXT,
    ligand_class_raw TEXT,
    structure_raw TEXT,
    identity_status TEXT NOT NULL DEFAULT 'unreviewed',
    source_comment TEXT,
    UNIQUE (source_version_id, source_record_id)
);

CREATE TABLE source_references (
    reference_id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(source_version_id),
    source_record_id TEXT NOT NULL,
    reference_code TEXT,
    citation_raw TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'candidate',
    source_comment TEXT,
    UNIQUE (source_version_id, source_record_id)
);

CREATE TABLE constant_records (
    record_id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(source_version_id),
    source_record_id TEXT NOT NULL,
    ligand_id TEXT NOT NULL REFERENCES ligands(ligand_id),
    metal_species_id TEXT NOT NULL REFERENCES metal_species(metal_species_id),
    equilibrium_raw TEXT,
    value_type TEXT NOT NULL,
    reported_value_text TEXT,
    numeric_value REAL,
    source_standardized_value_text TEXT,
    temperature_raw TEXT,
    temperature_c REAL,
    temperature_k REAL,
    ionic_strength_raw TEXT,
    ionic_strength_numeric REAL,
    solvent_raw TEXT,
    electrolyte_raw TEXT,
    uncertainty_raw TEXT,
    footnote_raw TEXT,
    source_comment TEXT,
    provenance_granularity TEXT NOT NULL,
    verification_status TEXT NOT NULL CHECK (
        verification_status IN ('candidate', 'reviewed', 'verified', 'rejected', 'superseded')
    ),
    quality_flags_json TEXT NOT NULL DEFAULT '[]',
    verified_reference_id TEXT REFERENCES source_references(reference_id),
    supersedes_record_id TEXT REFERENCES constant_records(record_id),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    UNIQUE (source_version_id, source_record_id)
);

CREATE TABLE ligand_metal_reference_candidates (
    link_id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(source_version_id),
    source_record_id TEXT NOT NULL,
    ligand_id TEXT NOT NULL REFERENCES ligands(ligand_id),
    metal_species_id TEXT NOT NULL REFERENCES metal_species(metal_species_id),
    reference_id TEXT REFERENCES source_references(reference_id),
    resolution_status TEXT NOT NULL CHECK (
        resolution_status IN ('resolved', 'missing_reference')
    ),
    not_used_flag INTEGER,
    source_comment TEXT,
    UNIQUE (source_version_id, source_record_id)
);

CREATE TABLE dataset_releases (
    release_id TEXT PRIMARY KEY,
    release_name TEXT NOT NULL,
    release_status TEXT NOT NULL CHECK (
        release_status IN ('candidate', 'reviewed', 'published', 'retired')
    ),
    intended_use TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    manifest_json TEXT NOT NULL
);

CREATE TABLE dataset_release_records (
    release_id TEXT NOT NULL REFERENCES dataset_releases(release_id),
    record_id TEXT NOT NULL REFERENCES constant_records(record_id),
    PRIMARY KEY (release_id, record_id)
);

CREATE TABLE review_events (
    review_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES constant_records(record_id),
    decision TEXT NOT NULL CHECK (decision IN ('reviewed', 'verified', 'rejected')),
    reviewer TEXT NOT NULL,
    reviewed_at_utc TEXT NOT NULL,
    reason TEXT NOT NULL,
    verified_reference_id TEXT REFERENCES source_references(reference_id),
    supersedes_record_id TEXT REFERENCES constant_records(record_id),
    decisions_file_sha256 TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE INDEX idx_constant_records_metal ON constant_records(metal_species_id);
CREATE INDEX idx_constant_records_ligand ON constant_records(ligand_id);
CREATE INDEX idx_constant_records_value_type ON constant_records(value_type);
CREATE INDEX idx_constant_records_numeric_value ON constant_records(numeric_value);
CREATE INDEX idx_constant_records_temperature_c ON constant_records(temperature_c);
CREATE INDEX idx_constant_records_ionic_strength
    ON constant_records(ionic_strength_numeric);
CREATE INDEX idx_constant_records_value_active_numeric
    ON constant_records(value_type, is_active, numeric_value);
CREATE INDEX idx_constant_records_status ON constant_records(verification_status, is_active);
CREATE INDEX idx_reference_candidates_pair
    ON ligand_metal_reference_candidates(ligand_id, metal_species_id);
CREATE INDEX idx_release_records_record ON dataset_release_records(record_id);
CREATE INDEX idx_review_events_record ON review_events(record_id);

CREATE VIEW active_constant_records AS
SELECT *
FROM constant_records
WHERE is_active = 1
  AND verification_status IN ('candidate', 'reviewed', 'verified');

CREATE VIEW verified_constant_records AS
SELECT *
FROM constant_records
WHERE is_active = 1
  AND verification_status = 'verified';
