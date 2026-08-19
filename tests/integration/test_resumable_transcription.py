from pathlib import Path

from ttac.asr.fake import FakeAdapter
from ttac.asr.protocol import WorkerRequest
from ttac.pipeline.transcribe import transcribe_requests
from ttac.runs.state import SQLiteLedger


def make_requests(tmp_path: Path, count: int = 3) -> list[WorkerRequest]:
    requests = []
    for index in range(count):
        audio = tmp_path / f"clip-{index}.wav"
        audio.write_bytes(b"synthetic")
        requests.append(
            WorkerRequest(
                transcription_run_id="tr-resume",
                utterance_id=f"utt-{index}",
                engine="fake",
                audio_path=audio,
                output_dir=tmp_path / "out",
                model_revision="fixture-v1",
                decoding={"language": "tr"},
            )
        )
    return requests


def test_resumable_transcription_reuses_successful_rows_without_duplicates(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3", "tr-resume")
    requests = make_requests(tmp_path)

    first = transcribe_requests(FakeAdapter(), requests, ledger)
    second = transcribe_requests(FakeAdapter(), requests, ledger)

    assert first.succeeded == 3
    assert first.reused == 0
    assert second.succeeded == 0
    assert second.reused == 3
    assert all(ledger.get_job(request.utterance_id, "fake").status == "succeeded" for request in requests)
    ledger.close()


def test_failed_and_skipped_results_remain_visible_in_ledger(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3", "tr-resume")
    requests = make_requests(tmp_path, count=2)

    summary = transcribe_requests(FakeAdapter(failure_mode="corrupt"), requests, ledger)

    assert summary.failed == 2
    assert all(ledger.get_job(request.utterance_id, "fake").status == "failed" for request in requests)
    ledger.close()
