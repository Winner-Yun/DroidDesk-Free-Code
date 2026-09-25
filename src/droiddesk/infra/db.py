"""SQLite schema, migrations, and repository layer for DroidDesk data persistence."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from droiddesk.core.models import (
    ApkInfo,
    BuildRecord,
    Device,
    Finding,
    Project,
    ScanResult,
    TestRun,
    TestStepResult,
)
from droiddesk.core.severity import Severity, Verdict

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

    def vacuum(self) -> None:
        """Run SQLite VACUUM to reclaim unused disk space."""
        with self._lock:
            self._connection.execute("VACUUM")

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

    def save_test_run(self, run: TestRun, apk_id: int | None = None) -> int:
        import dataclasses
        import json

        with self._lock:
            if apk_id is None:
                cursor_apk = self._connection.execute(
                    "SELECT id FROM apk WHERE file_hash = ?", (run.apk.file_hash,)
                )
                row_apk = cursor_apk.fetchone()
                if row_apk:
                    apk_id = int(row_apk[0])
                else:
                    self.save_apk(run.apk)
                    cursor_apk = self._connection.execute(
                        "SELECT id FROM apk WHERE file_hash = ?", (run.apk.file_hash,)
                    )
                    row_apk = cursor_apk.fetchone()
                    if row_apk:
                        apk_id = int(row_apk[0])

            steps_data = [dataclasses.asdict(s) for s in run.steps]
            steps_json = json.dumps(steps_data)
            started_at_str = run.started_at.isoformat()
            screenshot_str = str(run.screenshot_path) if run.screenshot_path else None
            verdict_str = run.verdict.value if hasattr(run.verdict, "value") else str(run.verdict)

            cursor = self._connection.execute(
                """
                INSERT INTO test_run (
                    apk_id, device_serial, profile_name, started_at,
                    duration_ms, verdict, steps_json, log_excerpt, screenshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    apk_id,
                    run.device_serial,
                    run.profile_name,
                    started_at_str,
                    run.duration_ms,
                    verdict_str,
                    steps_json,
                    run.log_excerpt,
                    screenshot_str,
                ),
            )
            self._connection.commit()
            return int(cursor.lastrowid or 0)

    def get_test_run(self, run_id: int) -> TestRun | None:
        import json
        from datetime import datetime

        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT t.id, t.apk_id, t.device_serial, t.profile_name, t.started_at,
                       t.duration_ms, t.verdict, t.steps_json, t.log_excerpt, t.screenshot,
                       a.file_path, a.file_hash, a.package_name, a.version_name, a.version_code
                FROM test_run t
                LEFT JOIN apk a ON t.apk_id = a.id
                WHERE t.id = ?
                """,
                (run_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        apk_info = ApkInfo(
            file_path=Path(row[10] or "unknown.apk"),
            file_hash=str(row[11] or ""),
            package_name=str(row[12] or "unknown"),
            version_name=str(row[13]) if row[13] else None,
            version_code=int(row[14]) if row[14] is not None else None,
        )
        steps_list: list[TestStepResult] = []
        try:
            raw_steps = json.loads(row[7] or "[]")
            for s in raw_steps:
                steps_list.append(
                    TestStepResult(
                        name=s.get("name", ""),
                        passed=bool(s.get("passed", False)),
                        duration_ms=int(s.get("duration_ms", 0)),
                        detail=s.get("detail", ""),
                    )
                )
        except Exception:
            pass

        started_dt = datetime.fromisoformat(row[4]) if row[4] else datetime.now()
        verdict = Verdict(row[6]) if row[6] in [v.value for v in Verdict] else Verdict.PASS
        screenshot_path = Path(row[9]) if row[9] else None

        return TestRun(
            apk=apk_info,
            device_serial=str(row[2]),
            profile_name=str(row[3]),
            started_at=started_dt,
            steps=steps_list,
            verdict=verdict,
            duration_ms=int(row[5] or 0),
            log_excerpt=row[8],
            screenshot_path=screenshot_path,
        )

    def list_test_runs(self, apk_id: int | None = None) -> list[dict[str, object]]:
        query = """
            SELECT t.id, t.apk_id, t.device_serial, t.profile_name, t.started_at,
                   t.duration_ms, t.verdict, a.package_name
            FROM test_run t
            LEFT JOIN apk a ON t.apk_id = a.id
        """
        params: tuple[object, ...] = ()
        if apk_id is not None:
            query += " WHERE t.apk_id = ?"
            params = (apk_id,)
        query += " ORDER BY t.started_at DESC"

        with self._lock:
            cursor = self._connection.execute(query, params)
            rows = cursor.fetchall()

        return [
            {
                "id": int(r[0]),
                "apk_id": int(r[1]) if r[1] is not None else None,
                "device_serial": str(r[2]),
                "profile_name": str(r[3]),
                "started_at": str(r[4]),
                "duration_ms": int(r[5] or 0),
                "verdict": str(r[6]),
                "package_name": str(r[7] or "Unknown"),
            }
            for r in rows
        ]

    def save_scan(self, scan: ScanResult, project_id: int | None = None) -> int:
        started_at_str = scan.started_at.isoformat()
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO scan (
                    project_id, target_type, target_path, started_at,
                    files_scanned, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    scan.target_type,
                    str(scan.target_path),
                    started_at_str,
                    scan.files_scanned,
                    scan.duration_ms,
                ),
            )
            scan_id = int(cursor.lastrowid or 0)

            for finding in scan.findings:
                severity_str = (
                    finding.severity.name
                    if hasattr(finding.severity, "name")
                    else str(finding.severity)
                )
                self._connection.execute(
                    """
                    INSERT INTO finding (
                        scan_id, rule_id, severity, file_path, line_number,
                        match_hash, redacted, suppressed, suppress_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scan_id,
                        finding.rule_id,
                        severity_str,
                        str(finding.file_path),
                        finding.line_number,
                        finding.match_hash,
                        finding.redacted,
                        1 if finding.suppressed else 0,
                        finding.suppress_note,
                    ),
                )
            self._connection.commit()
            return scan_id

    def get_scan(self, scan_id: int) -> ScanResult | None:
        from datetime import datetime

        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT id, project_id, target_type, target_path, started_at,
                       files_scanned, duration_ms
                FROM scan
                WHERE id = ?
                """,
                (scan_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            cursor_findings = self._connection.execute(
                """
                SELECT rule_id, severity, file_path, line_number, match_hash,
                       redacted, suppressed, suppress_note
                FROM finding
                WHERE scan_id = ?
                """,
                (scan_id,),
            )
            findings_rows = cursor_findings.fetchall()

        findings: list[Finding] = []
        for f in findings_rows:
            sev_str = str(f[1]).upper()
            try:
                sev = Severity[sev_str]
            except KeyError:
                sev = Severity.INFORMATIONAL
            findings.append(
                Finding(
                    rule_id=str(f[0]),
                    severity=sev,
                    file_path=Path(f[2]),
                    line_number=int(f[3]) if f[3] is not None else None,
                    match_hash=str(f[4]),
                    redacted=str(f[5]),
                    suppressed=bool(f[6]),
                    suppress_note=str(f[7]) if f[7] else None,
                )
            )

        started_dt = datetime.fromisoformat(row[4]) if row[4] else datetime.now()
        return ScanResult(
            target_type=str(row[2]),
            target_path=Path(row[3]),
            started_at=started_dt,
            findings=findings,
            files_scanned=int(row[5] or 0),
            duration_ms=int(row[6] or 0),
        )

    def list_scans(self, project_id: int | None = None) -> list[dict[str, object]]:
        query = """
            SELECT s.id, s.project_id, s.target_type, s.target_path, s.started_at,
                   s.files_scanned, s.duration_ms, COUNT(f.id) as finding_count
            FROM scan s
            LEFT JOIN finding f ON s.id = f.scan_id
        """
        params: tuple[object, ...] = ()
        if project_id is not None:
            query += " WHERE s.project_id = ?"
            params = (project_id,)
        query += " GROUP BY s.id ORDER BY s.started_at DESC"

        with self._lock:
            cursor = self._connection.execute(query, params)
            rows = cursor.fetchall()

        return [
            {
                "id": int(r[0]),
                "project_id": int(r[1]) if r[1] is not None else None,
                "target_type": str(r[2]),
                "target_path": str(r[3]),
                "started_at": str(r[4]),
                "files_scanned": int(r[5] or 0),
                "duration_ms": int(r[6] or 0),
                "finding_count": int(r[7] or 0),
            }
            for r in rows
        ]

    def get_build_record(self, record_id: int) -> BuildRecord | None:
        from datetime import datetime

        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT id, project_id, command, environment, gate_score,
                       gate_verdict, overridden, override_note, exit_code, started_at
                FROM build_record
                WHERE id = ?
                """,
                (record_id,),
            )
            r = cursor.fetchone()
        if not r:
            return None
        dt = datetime.fromisoformat(r[9]) if r[9] else datetime.now()
        return BuildRecord(
            id=int(r[0]),
            project_id=int(r[1]) if r[1] is not None else None,
            command=str(r[2]),
            environment=str(r[3]),
            gate_score=int(r[4]) if r[4] is not None else None,
            gate_verdict=str(r[5]) if r[5] else None,
            overridden=bool(r[6]),
            override_note=str(r[7]) if r[7] else None,
            exit_code=int(r[8]) if r[8] is not None else None,
            started_at=dt,
        )

    def list_build_records(self, project_id: int | None = None) -> list[BuildRecord]:
        from datetime import datetime

        query = """
            SELECT id, project_id, command, environment, gate_score,
                   gate_verdict, overridden, override_note, exit_code, started_at
            FROM build_record
        """
        params: tuple[object, ...] = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            params = (project_id,)
        query += " ORDER BY started_at DESC"

        with self._lock:
            cursor = self._connection.execute(query, params)
            rows = cursor.fetchall()

        records: list[BuildRecord] = []
        for r in rows:
            dt = datetime.fromisoformat(r[9]) if r[9] else datetime.now()
            records.append(
                BuildRecord(
                    id=int(r[0]),
                    project_id=int(r[1]) if r[1] is not None else None,
                    command=str(r[2]),
                    environment=str(r[3]),
                    gate_score=int(r[4]) if r[4] is not None else None,
                    gate_verdict=str(r[5]) if r[5] else None,
                    overridden=bool(r[6]),
                    override_note=str(r[7]) if r[7] else None,
                    exit_code=int(r[8]) if r[8] is not None else None,
                    started_at=dt,
                )
            )
        return records

    def list_report_history(self) -> list[dict[str, object]]:
        """Combine build_record (Release Gate), test_run (Test Run), and scan (Secret Scan)
        into a unified chronological history sorted by started_at DESC.
        """
        results: list[dict[str, object]] = []

        with self._lock:
            # Build records
            cursor_gates = self._connection.execute(
                """
                SELECT id, command, gate_verdict, gate_score, started_at, overridden
                FROM build_record
                ORDER BY started_at DESC
                """
            )
            for row in cursor_gates.fetchall():
                verdict = str(row[2] or "UNKNOWN")
                if row[5]:
                    verdict = "OVERRIDDEN"
                results.append(
                    {
                        "id": f"gate_{row[0]}",
                        "raw_id": int(row[0]),
                        "report_type": "gate",
                        "kind": "Release Gate",
                        "name": f"Release Gate ({row[1]})",
                        "verdict": verdict,
                        "when": str(row[4]),
                    }
                )

            # Test runs
            cursor_tests = self._connection.execute(
                """
                SELECT t.id, t.device_serial, t.profile_name, t.verdict,
                       t.started_at, a.package_name
                FROM test_run t
                LEFT JOIN apk a ON t.apk_id = a.id
                ORDER BY t.started_at DESC
                """
            )
            for row in cursor_tests.fetchall():
                pkg = row[5] or row[2] or "APK"
                results.append(
                    {
                        "id": f"test_{row[0]}",
                        "raw_id": int(row[0]),
                        "report_type": "test",
                        "kind": "Test Run",
                        "name": f"Test Run: {pkg} ({row[1]})",
                        "verdict": str(row[3] or "UNKNOWN"),
                        "when": str(row[4]),
                    }
                )

            # Secret scans
            cursor_scans = self._connection.execute(
                """
                SELECT s.id, s.target_type, s.target_path, s.started_at,
                       COUNT(f.id) as total_findings,
                       SUM(CASE WHEN f.severity = 'CRITICAL' THEN 1 ELSE 0 END) as critical_findings
                FROM scan s
                LEFT JOIN finding f ON s.id = f.scan_id
                GROUP BY s.id
                ORDER BY s.started_at DESC
                """
            )
            for row in cursor_scans.fetchall():
                target_name = Path(str(row[2])).name or str(row[2])
                crit = int(row[5] or 0)
                tot = int(row[4] or 0)
                if crit > 0:
                    verdict = "FAIL"
                elif tot > 0:
                    verdict = "WARN"
                else:
                    verdict = "PASS"
                results.append(
                    {
                        "id": f"scan_{row[0]}",
                        "raw_id": int(row[0]),
                        "report_type": "scan",
                        "kind": "Secret Scan",
                        "name": f"Secret Scan: {target_name}",
                        "verdict": verdict,
                        "when": str(row[3]),
                    }
                )

        results.sort(key=lambda x: str(x.get("when", "")), reverse=True)
        return results
