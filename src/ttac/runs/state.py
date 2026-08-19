"""Single-process SQLite lifecycle ledger for resumable pilot jobs."""

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LedgerError(RuntimeError):
    """Raised when a ledger transition or invariant is invalid."""


@dataclass(frozen=True)
class JobRecord:
    transcription_run_id: str
    utterance_id: str
    engine: str
    status: str
    retry_count: int
    started_at: float | None
    finished_at: float | None
    latency_ms: float | None
    peak_vram_mb: float | None
    error_reason: str | None
    result: dict[str, Any] | None
    output_checksum: str | None


class SQLiteLedger:
    """A one-orchestrator ledger; concurrency fencing is intentionally out of scope."""

    def __init__(self, path: str | Path, transcription_run_id: str, stale_after_seconds: float = 900) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.transcription_run_id = transcription_run_id
        self.stale_after_seconds = stale_after_seconds
        self._lock_path = self.path.with_name(f"{self.path.name}.lock")
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ledger_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                transcription_run_id TEXT NOT NULL,
                utterance_id TEXT NOT NULL,
                engine TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')),
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                started_at REAL,
                finished_at REAL,
                latency_ms REAL,
                peak_vram_mb REAL,
                error_reason TEXT,
                result_json TEXT,
                output_checksum TEXT,
                UNIQUE(transcription_run_id, utterance_id, engine)
            );
            CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status, id);
            """
        )
        existing = self._connection.execute(
            "SELECT value FROM ledger_meta WHERE key = 'transcription_run_id'"
        ).fetchone()
        if existing is None:
            self._connection.execute(
                "INSERT INTO ledger_meta(key, value) VALUES ('transcription_run_id', ?)",
                (self.transcription_run_id,),
            )
        elif existing["value"] != self.transcription_run_id:
            raise LedgerError("ledger belongs to a different transcription_run_id")
        self._connection.commit()

    def create_job(self, utterance_id: str, engine: str) -> None:
        if not utterance_id or not engine:
            raise LedgerError("utterance_id and engine must be non-empty")
        try:
            self._connection.execute(
                """
                INSERT INTO jobs(transcription_run_id, utterance_id, engine, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (self.transcription_run_id, utterance_id, engine, time.time()),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise LedgerError("duplicate job") from exc

    def claim_next(self) -> JobRecord | None:
        self.recover_stale()
        row = self._connection.execute(
            "SELECT id FROM jobs WHERE status = 'pending' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        now = time.time()
        self._connection.execute(
            "UPDATE jobs SET status = 'running', started_at = ?, finished_at = NULL WHERE id = ?",
            (now, row["id"]),
        )
        self._connection.commit()
        return self._record_by_id(row["id"])

    def complete_success(
        self,
        utterance_id: str,
        engine: str,
        result: dict[str, Any],
        output_checksum: str,
        peak_vram_mb: float | None = None,
    ) -> None:
        transcript = result.get("transcript")
        if not isinstance(transcript, str) or not transcript.strip():
            raise LedgerError("empty transcript cannot be successful")
        if not isinstance(output_checksum, str) or not output_checksum.strip():
            raise LedgerError("successful result requires output checksum")
        row = self._get_row(utterance_id, engine)
        self._require_running(row)
        now = time.time()
        latency_ms = (now - row["started_at"]) * 1000 if row["started_at"] else None
        self._connection.execute(
            """
            UPDATE jobs
            SET status = 'succeeded', finished_at = ?, latency_ms = ?, peak_vram_mb = ?,
                result_json = ?, output_checksum = ?, error_reason = NULL
            WHERE id = ?
            """,
            (now, latency_ms, peak_vram_mb, json.dumps(result, sort_keys=True), output_checksum, row["id"]),
        )
        self._connection.commit()

    def mark_failed(self, utterance_id: str, engine: str, error_reason: str, retry: bool = True) -> None:
        row = self._get_row(utterance_id, engine)
        self._require_running(row)
        status = "pending" if retry else "failed"
        self._connection.execute(
            """
            UPDATE jobs SET status = ?, retry_count = retry_count + 1, finished_at = ?,
                error_reason = ?, result_json = NULL, output_checksum = NULL
            WHERE id = ?
            """,
            (status, time.time(), error_reason, row["id"]),
        )
        self._connection.commit()

    def skip(self, utterance_id: str, engine: str, reason: str) -> None:
        row = self._get_row(utterance_id, engine)
        self._require_running(row)
        self._connection.execute(
            "UPDATE jobs SET status = 'skipped', finished_at = ?, error_reason = ? WHERE id = ?",
            (time.time(), reason, row["id"]),
        )
        self._connection.commit()

    def recover_stale(self, now: float | None = None) -> int:
        cutoff = (time.time() if now is None else now) - self.stale_after_seconds
        cursor = self._connection.execute(
            """
            UPDATE jobs SET status = 'pending', started_at = NULL, error_reason = 'stale recovery'
            WHERE status = 'running' AND started_at < ?
            """,
            (cutoff,),
        )
        self._connection.commit()
        return cursor.rowcount

    def get_job(self, utterance_id: str, engine: str) -> JobRecord | None:
        row = self._connection.execute(
            """
            SELECT * FROM jobs WHERE transcription_run_id = ? AND utterance_id = ? AND engine = ?
            """,
            (self.transcription_run_id, utterance_id, engine),
        ).fetchone()
        return self._record(row) if row is not None else None

    def export_snapshot(self, path: str | Path) -> None:
        destination = Path(path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        rows = self._connection.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(self._row_dict(row), ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(temporary, destination)

    def acquire_run_lock(self) -> None:
        try:
            descriptor = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise LedgerError("run is already locked") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))

    def release_run_lock(self) -> None:
        try:
            self._lock_path.unlink()
        except FileNotFoundError:
            pass

    def close(self) -> None:
        self._connection.close()

    def _get_row(self, utterance_id: str, engine: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM jobs WHERE transcription_run_id = ? AND utterance_id = ? AND engine = ?",
            (self.transcription_run_id, utterance_id, engine),
        ).fetchone()
        if row is None:
            raise LedgerError("job does not exist")
        return row

    @staticmethod
    def _require_running(row: sqlite3.Row) -> None:
        if row["status"] != "running":
            raise LedgerError(f"job is not running: {row['status']}")

    def _record_by_id(self, job_id: int) -> JobRecord:
        row = self._connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise LedgerError("job disappeared from ledger")
        return self._record(row)

    @staticmethod
    def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
        values = dict(row)
        if values.get("result_json") is not None:
            values["result"] = json.loads(values.pop("result_json"))
        else:
            values.pop("result_json", None)
        return values

    @classmethod
    def _record(cls, row: sqlite3.Row) -> JobRecord:
        values = cls._row_dict(row)
        return JobRecord(
            transcription_run_id=values["transcription_run_id"],
            utterance_id=values["utterance_id"],
            engine=values["engine"],
            status=values["status"],
            retry_count=values["retry_count"],
            started_at=values["started_at"],
            finished_at=values["finished_at"],
            latency_ms=values["latency_ms"],
            peak_vram_mb=values["peak_vram_mb"],
            error_reason=values["error_reason"],
            result=values.get("result"),
            output_checksum=values["output_checksum"],
        )
