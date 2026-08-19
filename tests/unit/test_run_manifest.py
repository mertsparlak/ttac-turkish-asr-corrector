from ttac.runs.manifest import (
    EvaluationInputs,
    TranscriptionInputs,
    build_evaluation_id,
    build_evaluation_manifest,
    build_transcription_manifest,
    build_transcription_run_id,
)


def transcription_inputs(**changes: object) -> TranscriptionInputs:
    values: dict[str, object] = {
        "source_fingerprints": {"manifest": "source-v1"},
        "benchmark_content_id": "benchmark-v1",
        "model_repository": "openai/whisper-small",
        "model_revision": "abc123",
        "dependency_lock_hash": "lock-v1",
        "decoding_settings": {"language": "tr", "temperature": 0},
        "seed": 42,
        "device_policy": "cuda-if-available",
    }
    values.update(changes)
    return TranscriptionInputs(**values)  # type: ignore[arg-type]


def test_transcription_run_id_is_deterministic_and_provenance_sensitive() -> None:
    first = build_transcription_run_id(transcription_inputs())
    second = build_transcription_run_id(transcription_inputs())
    changed = build_transcription_run_id(
        transcription_inputs(decoding_settings={"language": "tr", "temperature": 0.2})
    )

    assert first == second
    assert first.startswith("tr-")
    assert first != changed


def test_evaluation_id_changes_without_changing_transcription_id() -> None:
    transcription_id = build_transcription_run_id(transcription_inputs())
    base = EvaluationInputs(
        hypothesis_checksums={"utt-1": "sha256:a"},
        eligibility_manifest_checksum="eligibility-v1",
        normalizer_version="tr-v1",
        baseline_config_hash="baseline-v1",
        audit_disposition_hash="audit-v1",
        decision_gate_config_hash="gates-v1",
    )

    first = build_evaluation_id(base)
    changed_gate = build_evaluation_id(
        EvaluationInputs(
            **{**base.__dict__, "decision_gate_config_hash": "gates-v2"}
        )
    )

    assert transcription_id == build_transcription_run_id(transcription_inputs())
    assert first.startswith("ev-")
    assert first != changed_gate


def test_manifests_are_portable_and_include_their_stable_identity() -> None:
    transcription = transcription_inputs()
    transcription_manifest = build_transcription_manifest(transcription, created_at="2026-08-17T00:00:00Z")
    evaluation = EvaluationInputs(
        hypothesis_checksums={"utt-1": "sha256:a"},
        eligibility_manifest_checksum="eligibility-v1",
        normalizer_version="tr-v1",
        baseline_config_hash="baseline-v1",
        audit_disposition_hash="audit-v1",
        decision_gate_config_hash="gates-v1",
    )
    evaluation_manifest = build_evaluation_manifest(evaluation, created_at="2026-08-17T00:00:00Z")

    assert transcription_manifest["schema_version"] == "ttac-transcription/v1"
    assert transcription_manifest["transcription_run_id"] == build_transcription_run_id(transcription)
    assert transcription_manifest["created_at"] == "2026-08-17T00:00:00Z"
    assert evaluation_manifest["schema_version"] == "ttac-evaluation/v1"
    assert evaluation_manifest["evaluation_id"] == build_evaluation_id(evaluation)
