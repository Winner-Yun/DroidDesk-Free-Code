"""SQLite schema, migrations, and the Repository. Schema is Section 7, verbatim.

Never store a discovered secret's raw text - only a redacted preview and a hash of
the matched line (see the warning at the end of Section 7). Writing plaintext
credentials into the database would make DroidDesk the exposure it exists to catch.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from droiddesk.core.models import ApkInfo, BuildRecord, Device, Project

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

CREATE TABLE IF NOT EXISTS device_history (
    serial           TEXT PRIMARY KEY,
    model            TEXT,
    state            TEXT,
    android_version  TEXT,
    api_level        INTEGER,
    abi              TEXT,
    last_connected   TEXT NOT NULL
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
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        with self._lock:
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._migrate()

    def _migrate(self) -> None:
        # TODO(Phase 2): replace with numbered migration scripts applied in order,
        # tracked via schema_version, once the schema needs to evolve past v1.
        with self._lock:
            self._connection.executescript(SCHEMA)
            row = self._connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (CURRENT_SCHEMA_VERSION,)
                )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    # TODO(Phase 2+): save_test_run, save_scan, save_finding,
    # list_findings, save_build_record - one method per write/read the services
    # layer needs, backed by SQLAlchemy Core per Section 2.1.

    def save_apk(self, apk: ApkInfo) -> None:
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()

        query = """
            INSERT INTO apk (
                file_path, file_hash, package_name, version_name,
                version_code, target_sdk, min_sdk, size_bytes, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_hash) DO UPDATE SET
                file_path=excluded.file_path,
                package_name=excluded.package_name,
                version_name=excluded.version_name,
                version_code=excluded.version_code,
                target_sdk=excluded.target_sdk,
                min_sdk=excluded.min_sdk,
                size_bytes=excluded.size_bytes,
                analyzed_at=excluded.analyzed_at
        """

        with self._lock:
            self._connection.execute(
                query,
                (
                    str(apk.file_path),
                    apk.file_hash,
                    apk.package_name,
                    apk.version_name,
                    apk.version_code,
                    apk.target_sdk,
                    apk.min_sdk,
                    apk.size_bytes,
                    now,
                ),
            )
            self._connection.commit()

    def list_apks(self) -> list[ApkInfo]:
        """List all stored APK records, ordered with most recently analyzed first."""
        from datetime import datetime

        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT file_path, file_hash, package_name, version_name,
                       version_code, target_sdk, min_sdk, size_bytes, analyzed_at
                FROM apk
                ORDER BY analyzed_at DESC, id DESC
                """
            )
            rows = cursor.fetchall()

        results: list[ApkInfo] = []
        for row in rows:
            analyzed_dt = None
            if row[8]:
                try:
                    analyzed_dt = datetime.fromisoformat(row[8])
                except Exception:
                    analyzed_dt = None
            results.append(
                ApkInfo(
                    file_path=Path(row[0]),
                    file_hash=row[1],
                    package_name=row[2],
                    version_name=row[3],
                    version_code=row[4],
                    target_sdk=row[5],
                    min_sdk=row[6],
                    size_bytes=row[7] or 0,
                    analyzed_at=analyzed_dt,
                )
            )
        return results

    def get_apk_by_hash(self, file_hash: str) -> ApkInfo | None:
        """Fetch a single APK record by its file hash."""
        from datetime import datetime

        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT file_path, file_hash, package_name, version_name,
                       version_code, target_sdk, min_sdk, size_bytes, analyzed_at
                FROM apk
                WHERE file_hash = ?
                """,
                (file_hash,),
            )
            row = cursor.fetchone()

        if not row:
            return None
        analyzed_dt = None
        if row[8]:
            try:
                analyzed_dt = datetime.fromisoformat(row[8])
            except Exception:
                analyzed_dt = None
        return ApkInfo(
            file_path=Path(row[0]),
            file_hash=row[1],
            package_name=row[2],
            version_name=row[3],
            version_code=row[4],
            target_sdk=row[5],
            min_sdk=row[6],
            size_bytes=row[7] or 0,
            analyzed_at=analyzed_dt,
        )

    def delete_apk(self, file_hash: str) -> bool:
        """Delete an APK record by hash, safely removing any referencing test runs."""
        with self._lock:
            cursor = self._connection.execute(
                "SELECT id FROM apk WHERE file_hash = ?", (file_hash,)
            )
            row = cursor.fetchone()
            if not row:
                return False
            apk_id = row[0]
            self._connection.execute("DELETE FROM test_run WHERE apk_id = ?", (apk_id,))
            self._connection.execute("DELETE FROM apk WHERE id = ?", (apk_id,))
            self._connection.commit()
            return True

    def record_device(self, device: Device) -> None:
        """Persist or update an emulator / device in connection history."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        query = """
            INSERT INTO device_history (
                serial, model, state, android_version, api_level, abi, last_connected
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(serial) DO UPDATE SET
                model=COALESCE(excluded.model, device_history.model),
                state=excluded.state,
                android_version=COALESCE(
                    excluded.android_version, device_history.android_version
                ),
                api_level=COALESCE(excluded.api_level, device_history.api_level),
                abi=COALESCE(excluded.abi, device_history.abi),
                last_connected=excluded.last_connected
        """
        with self._lock:
            self._connection.execute(
                query,
                (
                    device.serial,
                    device.model or device.serial,
                    device.state,
                    device.android_version or "-",
                    device.api_level or 0,
                    device.abi or "-",
                    now,
                ),
            )
            self._connection.commit()

    def list_device_history(self) -> list[dict[str, object]]:
        """List all historically connected emulators and physical devices."""
        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT serial, model, state, android_version, api_level, abi, last_connected
                FROM device_history
                ORDER BY last_connected DESC
                """
            )
            rows = cursor.fetchall()

        return [
            {
                "serial": str(row[0]),
                "model": str(row[1] or row[0]),
                "state": str(row[2] or "device"),
                "android_version": str(row[3] or "-"),
                "api_level": int(row[4] or 0),
                "abi": str(row[5] or "-"),
                "last_connected": str(row[6]),
            }
            for row in rows
        ]

    def save_build_record(self, record: BuildRecord) -> int:
        started_at_str = record.started_at.isoformat()
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO build_record (
                    project_id, command, environment, gate_score,
                    gate_verdict, overridden, override_note, exit_code, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.project_id,
                    record.command,
                    record.environment,
                    record.gate_score,
                    record.gate_verdict,
                    1 if record.overridden else 0,
                    record.override_note,
                    record.exit_code,
                    started_at_str,
                ),
            )
            self._connection.commit()
            return int(cursor.lastrowid or 0)

    def get_project_by_root(self, root_path: Path) -> Project | None:
        from datetime import datetime

        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT id, name, root_path, package_name, created_at, last_opened
                FROM project
                WHERE root_path = ?
                """,
                (str(root_path.resolve()),),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        created_at = datetime.fromisoformat(row[4]) if row[4] else None
        last_opened = datetime.fromisoformat(row[5]) if row[5] else None
        return Project(
            id=int(row[0]),
            name=str(row[1]),
            root_path=Path(row[2]),
            package_name=str(row[3]) if row[3] else None,
            created_at=created_at,
            last_opened=last_opened,
        )

    def save_project(self, project: Project) -> int:
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        created_at_str = project.created_at.isoformat() if project.created_at else now
        last_opened_str = project.last_opened.isoformat() if project.last_opened else now
        root_str = str(project.root_path.resolve())

        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO project (name, root_path, package_name, created_at, last_opened)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(root_path) DO UPDATE SET
                    name=excluded.name,
                    package_name=excluded.package_name,
                    last_opened=excluded.last_opened
                """,
                (project.name, root_str, project.package_name, created_at_str, last_opened_str),
            )
            self._connection.commit()
            return int(cursor.lastrowid or (project.id or 0))
