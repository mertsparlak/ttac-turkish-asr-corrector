"""Stable identities for transcription and evaluation artifacts."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TranscriptionInputs:
    source_fingerprints: Mapping[str, str]
    benchmark_content_id: str
    model_repository: str
    model_revision: str
    dependency_lock_hash: str
    decoding_settings: Mapping[str, Any]
    seed: int
    device_policy: str


@dataclass(frozen=True)
class EvaluationInputs:
    hypothesis_checksums: Mapping[str, str]
    eligibility_manifest_checksum: str
    normalizer_version: str
    baseline_config_hash: str
    audit_disposition_hash: str
    decision_gate_config_hash: str


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_transcription_run_id(inputs: TranscriptionInputs) -> str:
    return f"tr-{_digest(inputs)[:24]}"


def build_evaluation_id(inputs: EvaluationInputs) -> str:
    return f"ev-{_digest(inputs)[:24]}"


def build_transcription_manifest(
    inputs: TranscriptionInputs, *, created_at: str, transcription_run_id: str | None = None
) -> dict[str, Any]:
    """Return a portable, immutable manifest payload for one transcription run."""

    return {
        "schema_version": "ttac-transcription/v1",
        "transcription_run_id": transcription_run_id or build_transcription_run_id(inputs),
        "created_at": created_at,
        **_jsonable(asdict(inputs)),
    }


def build_evaluation_manifest(
    inputs: EvaluationInputs, *, created_at: str, evaluation_id: str | None = None
) -> dict[str, Any]:
    """Return a portable, immutable manifest payload for one evaluation pass."""

    return {
        "schema_version": "ttac-evaluation/v1",
        "evaluation_id": evaluation_id or build_evaluation_id(inputs),
        "created_at": created_at,
        **_jsonable(asdict(inputs)),
    }
