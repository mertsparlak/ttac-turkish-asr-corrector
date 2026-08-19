import json
import time
from pathlib import Path

import pytest

from ttac.runs.state import LedgerError, SQLiteLedger


def test_ledger_claims_completes_and_exports_successful_job(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "run.sqlite3", "tr-run-1", stale_after_seconds=60)
    ledger.create_job("utt-1", "fake")

    claimed = ledger.claim_next()
    assert claimed is not None
    assert claimed.status == "running"

    ledger.complete_success(
        "utt-1",
        "fake",
        {"transcript": "Merhaba", "latency_ms": 12.5},
        "sha256:result-1",
    )
    record = ledger.get_job("utt-1", "fake")
    assert record is not None
    assert record.status == "succeeded"
    assert record.output_checksum == "sha256:result-1"

    snapshot = tmp_path / "snapshot.jsonl"
    ledger.export_snapshot(snapshot)
    exported = [json.loads(line) for line in snapshot.read_text(encoding="utf-8").splitlines()]
    assert exported[0]["status"] == "succeeded"


def test_ledger_rejects_duplicate_jobs_and_empty_success(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "run.sqlite3", "tr-run-1")
    ledger.create_job("utt-1", "fake")
    with pytest.raises(LedgerError, match="duplicate"):
        ledger.create_job("utt-1", "fake")

    ledger.claim_next()
    with pytest.raises(LedgerError, match="empty"):
        ledger.complete_success("utt-1", "fake", {"transcript": ""}, "sha256:empty")


def test_ledger_rejects_success_without_output_checksum(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "run.sqlite3", "tr-run-1")
    ledger.create_job("utt-1", "fake")
    ledger.claim_next()

    with pytest.raises(LedgerError, match="checksum"):
        ledger.complete_success("utt-1", "fake", {"transcript": "ok"}, "")


def test_ledger_recovers_stale_running_job_without_touching_success(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "run.sqlite3", "tr-run-1", stale_after_seconds=1)
    ledger.create_job("utt-2", "fake")
    ledger.create_job("utt-1", "fake")
    ledger.claim_next()
    ledger.complete_success("utt-2", "fake", {"transcript": "ok"}, "sha256:ok")
    ledger.claim_next()

    ledger._connection.execute(
        "UPDATE jobs SET started_at = ? WHERE utterance_id = ?",
        (time.time() - 5, "utt-1"),
    )
    ledger._connection.commit()
    assert ledger.recover_stale() == 1
    assert ledger.get_job("utt-1", "fake").status == "pending"  # type: ignore[union-attr]
    assert ledger.get_job("utt-2", "fake").status == "succeeded"  # type: ignore[union-attr]


def test_run_lock_rejects_second_owner(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "run.sqlite3", "tr-run-1")
    ledger.acquire_run_lock()
    second = SQLiteLedger(tmp_path / "run.sqlite3", "tr-run-1")
    with pytest.raises(LedgerError, match="already locked"):
        second.acquire_run_lock()
    ledger.release_run_lock()
