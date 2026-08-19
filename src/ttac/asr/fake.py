"""Deterministic fake ASR adapter used for default CI and pipeline tests."""

import hashlib

from ttac.asr.base import AdapterCapabilities, AdapterStatus
from ttac.asr.protocol import WorkerRequest, WorkerResult


class FakeAdapter:
    def __init__(self, *, failure_mode: str | None = None) -> None:
        allowed = {None, "empty", "corrupt", "oom", "timeout", "transient"}
        if failure_mode not in allowed:
            raise ValueError(f"unsupported fake failure mode: {failure_mode}")
        self.failure_mode = failure_mode

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            engine="fake",
            model_revision="fixture-v1",
            status=AdapterStatus.READY,
            supports_official_context=False,
            device="cpu",
        )

    def transcribe(self, request: WorkerRequest) -> WorkerResult:
        if request.decoding.get("official_context") and not self.capabilities().supports_official_context:
            return WorkerResult(
                transcription_run_id=request.transcription_run_id,
                utterance_id=request.utterance_id,
                engine=request.engine,
                status="skipped",
                error_reason="not_applicable",
            )
        if not request.audio_path.exists():
            return self._failed(request, "missing_audio")
        if self.failure_mode is not None:
            reasons = {
                "empty": "empty_transcript",
                "corrupt": "corrupt_audio",
                "oom": "out_of_memory",
                "timeout": "timeout",
                "transient": "transient_failure",
            }
            return self._failed(request, reasons[self.failure_mode])
        transcript = f"fixture transcript for {request.utterance_id}"
        checksum = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
        return WorkerResult(
            transcription_run_id=request.transcription_run_id,
            utterance_id=request.utterance_id,
            engine=request.engine,
            status="succeeded",
            transcript=transcript,
            output_checksum=f"sha256:{checksum}",
        )

    @staticmethod
    def _failed(request: WorkerRequest, reason: str) -> WorkerResult:
        return WorkerResult(
            transcription_run_id=request.transcription_run_id,
            utterance_id=request.utterance_id,
            engine=request.engine,
            status="failed",
            error_reason=reason,
        )
