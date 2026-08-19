from pathlib import Path

import pytest

from ttac.data.qc import qc_read_recording, qc_spontaneous_recording
from ttac.data.schema import (
    ParticipantPrivateStore,
    build_eligibility_manifest,
    public_safe_export,
)


def test_qc_accepts_clear_turkishized_pronunciation_as_variant(tmp_path: Path) -> None:
    result = qc_read_recording(
        reference="CUDA out of memory hatası",
        observed="kuda out of memory hatası",
        audio_exists=True,
        consent_status="active",
        pronunciation_variant=True,
        pronunciation_clear=True,
    )

    assert result.status == "passed"
    assert result.pronunciation_variant is True


def test_qc_rejects_read_mismatch_and_prompt_only_spontaneous_audio(tmp_path: Path) -> None:
    read_result = qc_read_recording(
        reference="PyTorch ile eğitim",
        observed="başka bir cümle",
        audio_exists=True,
        consent_status="active",
    )
    spontaneous_result = qc_spontaneous_recording(
        prompt="Modeli nasıl eğittin?",
        manual_reference=None,
        audio_exists=True,
        consent_status="active",
    )

    assert read_result.status == "failed"
    assert "content_mismatch" in read_result.reasons
    assert spontaneous_result.status == "failed"
    assert "missing_manual_reference" in spontaneous_result.reasons


def test_withdrawal_quarantines_then_purges_private_speaker_data(tmp_path: Path) -> None:
    speaker_dir = tmp_path / "participants" / "spk-abc"
    speaker_dir.mkdir(parents=True)
    (speaker_dir / "utterance.wav").write_bytes(b"private")
    manifest = build_eligibility_manifest(
        [{"speaker_id": "spk-abc", "consent_status": "active", "usage_scope": "pilot"}]
    )
    store = ParticipantPrivateStore(tmp_path)

    withdrawn = store.withdraw("spk-abc", manifest, requested_at=1_000)
    assert withdrawn.manifest.records["spk-abc"]["consent_status"] == "withdrawn"
    assert withdrawn.quarantine_path.exists()

    deleted = store.purge_expired(now=1_000 + 7 * 24 * 60 * 60 + 1)
    assert deleted == 1
    assert not withdrawn.quarantine_path.exists()
    assert withdrawn.exclusion_token


def test_public_safe_export_rejects_private_fields_and_paths() -> None:
    with pytest.raises(ValueError, match="private field"):
        public_safe_export([{"speaker_id": "spk-a", "client_id": "client-a"}])
    with pytest.raises(ValueError, match="path"):
        public_safe_export([{"clip_id": "clip-a", "path": "C:\\private\\clip.wav"}])
