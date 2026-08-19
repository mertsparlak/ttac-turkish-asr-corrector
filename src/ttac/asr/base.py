"""Engine-neutral adapter capabilities and protocol."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ttac.asr.protocol import WorkerRequest, WorkerResult


class AdapterStatus(StrEnum):
    READY = "ready"
    INCOMPLETE_RESOURCE = "incomplete_resource"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class AdapterCapabilities:
    engine: str
    model_revision: str
    status: AdapterStatus
    supports_official_context: bool
    device: str


class ASRAdapter(Protocol):
    def capabilities(self) -> AdapterCapabilities:
        ...

    def transcribe(self, request: WorkerRequest) -> WorkerResult:
        ...
