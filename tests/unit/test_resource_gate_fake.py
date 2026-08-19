from pathlib import Path

from ttac.asr.fake import FakeAdapter
from ttac.asr.protocol import WorkerRequest
from ttac.pipeline.resource_gate import run_resource_gate


def test_fake_resource_gate_records_25_clip_capability_and_allows_lane(tmp_path: Path) -> None:
    requests = []
    for index in range(25):
        audio = tmp_path / f"clip-{index}.wav"
        audio.write_bytes(b"synthetic")
        requests.append(
            WorkerRequest(
                transcription_run_id="tr-gate",
                utterance_id=f"utt-{index}",
                engine="fake",
                audio_path=audio,
                output_dir=tmp_path / "out",
                model_revision="fixture-v1",
                decoding={"language": "tr"},
            )
        )

    result = run_resource_gate(FakeAdapter(), requests)

    assert result.status == "allowed"
    assert result.clip_count == 25
    assert result.succeeded == 25
    assert result.coverage == 1.0
    assert result.throughput_clips_per_second > 0
