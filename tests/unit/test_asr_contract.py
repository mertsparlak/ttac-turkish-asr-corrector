from pathlib import Path

from ttac.asr.base import AdapterStatus
from ttac.asr.fake import FakeAdapter
from ttac.asr.protocol import WorkerRequest


def make_request(tmp_path: Path, *, utterance_id: str = "utt-1", official_context: bool = False) -> WorkerRequest:
    audio = tmp_path / f"{utterance_id}.wav"
    audio.write_bytes(b"synthetic-audio")
    return WorkerRequest(
        transcription_run_id="tr-fixture",
        utterance_id=utterance_id,
        engine="fake",
        audio_path=audio,
        output_dir=tmp_path / "out",
        model_revision="fixture-v1",
        decoding={"language": "tr", "official_context": official_context},
    )


def test_fake_adapter_returns_deterministic_success_with_capability_receipt(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    request = make_request(tmp_path)

    first = adapter.transcribe(request)
    second = adapter.transcribe(request)

    assert first.to_dict() == second.to_dict()
    assert first.status == "succeeded"
    assert first.transcript == "fixture transcript for utt-1"
    assert first.output_checksum and first.output_checksum.startswith("sha256:")
    assert adapter.capabilities().status == AdapterStatus.READY


def test_fake_adapter_reports_failure_modes_and_unsupported_context(tmp_path: Path) -> None:
    assert FakeAdapter(failure_mode="empty").transcribe(make_request(tmp_path)).error_reason == "empty_transcript"
    assert FakeAdapter(failure_mode="corrupt").transcribe(make_request(tmp_path)).error_reason == "corrupt_audio"
    assert FakeAdapter(failure_mode="oom").transcribe(make_request(tmp_path)).error_reason == "out_of_memory"
    assert FakeAdapter(failure_mode="timeout").transcribe(make_request(tmp_path)).error_reason == "timeout"
    assert FakeAdapter().transcribe(make_request(tmp_path, official_context=True)).status == "skipped"
    assert FakeAdapter().transcribe(make_request(tmp_path, official_context=True)).error_reason == "not_applicable"
