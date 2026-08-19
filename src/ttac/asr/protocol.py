"""Small, versioned JSON contract shared by core and engine workers."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "ttac-worker/v1"


class ProtocolError(ValueError):
    """Raised when a worker request or result violates the protocol."""


@dataclass(frozen=True)
class WorkerRequest:
    transcription_run_id: str
    utterance_id: str
    engine: str
    audio_path: Path
    output_dir: Path
    model_revision: str
    decoding: Mapping[str, Any] = field(default_factory=dict)
    protocol_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol version: {self.protocol_version}")
        for name in ("transcription_run_id", "utterance_id", "engine", "model_revision"):
            if not getattr(self, name):
                raise ProtocolError(f"{name} must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "transcription_run_id": self.transcription_run_id,
            "utterance_id": self.utterance_id,
            "engine": self.engine,
            "audio_path": self.audio_path.as_posix(),
            "output_dir": self.output_dir.as_posix(),
            "model_revision": self.model_revision,
            "decoding": dict(self.decoding),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorkerRequest":
        try:
            return cls(
                protocol_version=data["protocol_version"],
                transcription_run_id=data["transcription_run_id"],
                utterance_id=data["utterance_id"],
                engine=data["engine"],
                audio_path=Path(data["audio_path"]),
                output_dir=Path(data["output_dir"]),
                model_revision=data["model_revision"],
                decoding=data.get("decoding", {}),
            )
        except (KeyError, TypeError) as exc:
            raise ProtocolError(f"invalid worker request: {exc}") from exc


@dataclass(frozen=True)
class WorkerResult:
    transcription_run_id: str
    utterance_id: str
    engine: str
    status: str
    transcript: str | None = None
    output_checksum: str | None = None
    error_reason: str | None = None
    protocol_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise ProtocolError(f"unsupported protocol version: {self.protocol_version}")
        if self.status not in {"succeeded", "failed", "skipped"}:
            raise ProtocolError(f"invalid worker result status: {self.status}")
        if self.status == "succeeded" and not (self.transcript or "").strip():
            raise ProtocolError("empty transcript is not a successful result")
        if self.status == "succeeded" and not self.output_checksum:
            raise ProtocolError("successful result requires output_checksum")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "transcription_run_id": self.transcription_run_id,
            "utterance_id": self.utterance_id,
            "engine": self.engine,
            "status": self.status,
            "transcript": self.transcript,
            "output_checksum": self.output_checksum,
            "error_reason": self.error_reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorkerResult":
        try:
            return cls(
                protocol_version=data["protocol_version"],
                transcription_run_id=data["transcription_run_id"],
                utterance_id=data["utterance_id"],
                engine=data["engine"],
                status=data["status"],
                transcript=data.get("transcript"),
                output_checksum=data.get("output_checksum"),
                error_reason=data.get("error_reason"),
            )
        except (KeyError, TypeError) as exc:
            raise ProtocolError(f"invalid worker result: {exc}") from exc
