from pathlib import Path

import pytest

from ttac.asr.protocol import ProtocolError, WorkerRequest, WorkerResult


def test_worker_request_round_trips_with_versioned_schema(tmp_path: Path) -> None:
    request = WorkerRequest(
        transcription_run_id="tr-run-1",
        utterance_id="utt-1",
        engine="fake",
        audio_path=tmp_path / "audio.wav",
        output_dir=tmp_path / "out",
        model_revision="fixture-v1",
        decoding={"language": "tr"},
    )

    restored = WorkerRequest.from_dict(request.to_dict())

    assert restored == request
    assert restored.protocol_version == "ttac-worker/v1"


def test_worker_result_rejects_empty_success_transcript() -> None:
    with pytest.raises(ProtocolError, match="empty transcript"):
        WorkerResult.from_dict(
            {
                "protocol_version": "ttac-worker/v1",
                "transcription_run_id": "tr-run-1",
                "utterance_id": "utt-1",
                "engine": "fake",
                "status": "succeeded",
                "transcript": "",
                "output_checksum": "sha256:empty",
            }
        )
