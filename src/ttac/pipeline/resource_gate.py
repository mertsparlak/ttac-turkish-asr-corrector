"""Small deterministic capability/resource gate for ASR adapters."""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from ttac.asr.base import ASRAdapter
from ttac.asr.protocol import WorkerRequest


@dataclass(frozen=True)
class ResourceGateResult:
    engine: str
    status: str
    clip_count: int
    succeeded: int
    failed: int
    skipped: int
    coverage: float
    throughput_clips_per_second: float
    projected_duration_seconds: float
    device: str
    peak_vram_mb: float | None
    retries: int
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "ttac-resource-gate/v1",
            "engine": self.engine,
            "status": self.status,
            "clip_count": self.clip_count,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "coverage": self.coverage,
            "throughput_clips_per_second": self.throughput_clips_per_second,
            "projected_duration_seconds": self.projected_duration_seconds,
            "device": self.device,
            "peak_vram_mb": self.peak_vram_mb,
            "retries": self.retries,
            "reason": self.reason,
        }


def run_resource_gate(
    adapter: ASRAdapter,
    requests: Sequence[WorkerRequest],
    *,
    max_clips: int = 25,
    minimum_coverage: float = 0.98,
) -> ResourceGateResult:
    selected = list(requests[:max_clips])
    started = time.perf_counter()
    succeeded = failed = skipped = 0
    for request in selected:
        result = adapter.transcribe(request)
        if result.status == "succeeded":
            succeeded += 1
        elif result.status == "skipped":
            skipped += 1
        else:
            failed += 1
    elapsed = max(time.perf_counter() - started, 1e-9)
    clip_count = len(selected)
    coverage = succeeded / clip_count if clip_count else 0.0
    throughput = succeeded / elapsed if succeeded else 0.0
    status = "allowed" if clip_count and coverage >= minimum_coverage else "incomplete_resource"
    reason = None if status == "allowed" else "coverage_below_threshold"
    return ResourceGateResult(
        engine=adapter.capabilities().engine,
        status=status,
        clip_count=clip_count,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        coverage=coverage,
        throughput_clips_per_second=throughput,
        projected_duration_seconds=(clip_count / throughput if throughput else float("inf")),
        device=adapter.capabilities().device,
        peak_vram_mb=None,
        retries=0,
        reason=reason,
    )
