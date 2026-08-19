"""Sequential, resumable adapter orchestration over the SQLite ledger."""

from collections.abc import Sequence
from dataclasses import dataclass

from ttac.asr.base import ASRAdapter
from ttac.asr.protocol import WorkerRequest, WorkerResult
from ttac.runs.state import SQLiteLedger


@dataclass(frozen=True)
class TranscriptionSummary:
    total: int
    succeeded: int
    failed: int
    skipped: int
    reused: int
    retries: int


def transcribe_requests(
    adapter: ASRAdapter,
    requests: Sequence[WorkerRequest],
    ledger: SQLiteLedger,
    *,
    max_attempts: int = 1,
) -> TranscriptionSummary:
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    request_by_utterance = {request.utterance_id: request for request in requests}
    reused = 0
    for request in requests:
        existing = ledger.get_job(request.utterance_id, request.engine)
        if existing is None:
            ledger.create_job(request.utterance_id, request.engine)
        elif existing.status == "succeeded":
            reused += 1

    succeeded = failed = skipped = retries = 0
    ledger.acquire_run_lock()
    try:
        while True:
            job = ledger.claim_next()
            if job is None:
                break
            request = request_by_utterance[job.utterance_id]
            try:
                result = adapter.transcribe(request)
            except Exception as exc:  # pragma: no cover - defensive adapter boundary  # noqa: BLE001
                result = WorkerResult(
                    transcription_run_id=request.transcription_run_id,
                    utterance_id=request.utterance_id,
                    engine=request.engine,
                    status="failed",
                    error_reason=f"adapter_exception:{type(exc).__name__}",
                )
            if result.status == "succeeded":
                ledger.complete_success(
                    request.utterance_id,
                    request.engine,
                    result.to_dict(),
                    result.output_checksum or "",
                )
                succeeded += 1
            elif result.status == "skipped":
                ledger.skip(request.utterance_id, request.engine, result.error_reason or "skipped")
                skipped += 1
            else:
                should_retry = (
                    result.error_reason == "transient_failure" and job.retry_count + 1 < max_attempts
                )
                ledger.mark_failed(
                    request.utterance_id,
                    request.engine,
                    result.error_reason or "adapter_failure",
                    retry=should_retry,
                )
                retries += int(should_retry)
                if not should_retry:
                    failed += 1
    finally:
        ledger.release_run_lock()
    return TranscriptionSummary(
        total=len(requests),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        reused=reused,
        retries=retries,
    )
