"""SQLite schema, migrations, and the Repository. Schema is Section 7, verbatim.

Never store a discovered secret's raw text — only a redacted preview and a hash of
the matched line (see the warning at the end of Section 7). Writing plaintext
credentials into the database would make DroidDesk the exposure it exists to catch.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS project (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    root_path     TEXT NOT NULL UNIQUE,
    package_name  TEXT,
    created_at    TEXT NOT NULL,
    last_opened   TEXT
);

CREATE TABLE IF NOT EXISTS apk (
    id            INTEGER PRIMARY KEY,
    file_path     TEXT NOT NULL,
    file_hash     TEXT NOT NULL,
    package_name  TEXT NOT NULL,
    version_name  TEXT,
    version_code  INTEGER,
    target_sdk    INTEGER,
    min_sdk       INTEGER,
    size_bytes    INTEGER,
    analyzed_at   TEXT NOT NULL,
    UNIQUE(file_hash)
);

CREATE TABLE IF NOT EXISTS test_run (
    id             INTEGER PRIMARY KEY,
    apk_id         INTEGER REFERENCES apk(id),
    device_serial  TEXT NOT NULL,
    profile_name   TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    duration_ms    INTEGER,
    verdict        TEXT NOT NULL,
    steps_json     TEXT NOT NULL,
    log_excerpt    TEXT,
    screenshot     TEXT
);

CREATE TABLE IF NOT EXISTS scan (
    id             INTEGER PRIMARY KEY,
    project_id     INTEGER REFERENCES project(id),
    target_type    TEXT NOT NULL,
    target_path    TEXT NOT NULL,
    started_at     TEXT NOT NULL,
    files_scanned  INTEGER,
    duration_ms    INTEGER
);

CREATE TABLE IF NOT EXISTS finding (
    id             INTEGER PRIMARY KEY,
    scan_id        INTEGER REFERENCES scan(id) ON DELETE CASCADE,
    rule_id        TEXT NOT NULL,
    severity       TEXT NOT NULL,
    file_path      TEXT NOT NULL,
    line_number    INTEGER,
    match_hash     TEXT NOT NULL,
    redacted       TEXT NOT NULL,
    suppressed     INTEGER DEFAULT 0,
    suppress_note  TEXT
);

CREATE TABLE IF NOT EXISTS build_record (
    id             INTEGER PRIMARY KEY,
    project_id     INTEGER REFERENCES project(id),
    command        TEXT NOT NULL,
    environment    TEXT NOT NULL,
    gate_score     INTEGER,
    gate_verdict   TEXT,
    overridden     INTEGER DEFAULT 0,
    override_note  TEXT,
    exit_code      INTEGER,
    started_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_finding_scan ON finding(scan_id);
CREATE INDEX IF NOT EXISTS idx_test_apk     ON test_run(apk_id);
CREATE INDEX IF NOT EXISTS idx_build_proj   ON build_record(project_id, started_at DESC);
"""

CURRENT_SCHEMA_VERSION = 1


class Repository:
    """Owns the SQLite connection and all query construction. The only place
    outside `infra/` this is used from is the `services/` layer.
    """

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path)
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        # TODO(Phase 2): replace with numbered migration scripts applied in order,
        # tracked via schema_version, once the schema needs to evolve past v1.
        self._connection.executescript(SCHEMA)
        row = self._connection.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self._connection.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (CURRENT_SCHEMA_VERSION,)
            )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    # TODO(Phase 2+): save_apk, save_test_run, save_scan, save_finding,
    # list_findings, save_build_record — one method per write/read the services
    # layer needs, backed by SQLAlchemy Core per Section 2.1.
