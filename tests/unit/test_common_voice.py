import csv
import json
from pathlib import Path

import pytest

from ttac.data.common_voice import select_common_voice, verify_selection_manifest


def write_common_voice_fixture(root: Path) -> None:
    rows = [
        {"client_id": "client-a", "path": "a.mp3", "sentence": "Merhaba", "locale": "tr", "split": "train"},
        {"client_id": "client-b", "path": "b.mp3", "sentence": "Günaydın", "locale": "tr", "split": "train"},
        {"client_id": "client-c", "path": "c.mp3", "sentence": "İyi akşamlar", "locale": "tr", "split": "test"},
        {"client_id": "client-d", "path": "d.mp3", "sentence": "Nasılsın", "locale": "en", "split": "train"},
    ]
    for row in rows:
        (root / row["path"]).write_bytes(f"audio-{row['client_id']}".encode())
    with (root / "validated.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_common_voice_selection_is_deterministic_and_public_safe(tmp_path: Path) -> None:
    write_common_voice_fixture(tmp_path)

    first = select_common_voice(tmp_path, limit=2, seed=42, source_version="cv26", split="train")
    second = select_common_voice(tmp_path, limit=2, seed=42, source_version="cv26", split="train")

    assert first.to_dict() == second.to_dict()
    assert len(first.selected_clips) == 2
    assert all(clip["speaker_id"].startswith("spk-") for clip in first.selected_clips)
    assert "client_id" not in json.dumps(first.to_dict())
    assert first.speaker_distribution
    assert first.source_checksums


def test_common_voice_selection_records_missing_clip_replacement(tmp_path: Path) -> None:
    write_common_voice_fixture(tmp_path)
    (tmp_path / "a.mp3").unlink()

    manifest = select_common_voice(tmp_path, limit=2, seed=42, source_version="cv26", split="train")

    assert manifest.replacement_policy["missing_source"] == "excluded"
    assert all(clip["path"] != "a.mp3" for clip in manifest.selected_clips)


def test_common_voice_manifest_rejects_changed_metadata(tmp_path: Path) -> None:
    write_common_voice_fixture(tmp_path)
    manifest = select_common_voice(tmp_path, limit=2, seed=42, source_version="cv26", split="train")
    verify_selection_manifest(tmp_path, manifest)
    (tmp_path / "validated.tsv").write_text(
        (tmp_path / "validated.tsv").read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="metadata checksum"):
        verify_selection_manifest(tmp_path, manifest)


def test_repository_fixture_runs_without_network() -> None:
    fixture = Path("tests/fixtures/data/common_voice")
    manifest = select_common_voice(fixture, limit=2, seed=7, source_version="fixture-v1", split="train")
    assert len(manifest.selected_clips) == 2
    verify_selection_manifest(fixture, manifest)


def test_common_voice_uses_standard_split_file_without_split_column(tmp_path: Path) -> None:
    rows = [
        {"client_id": "client-a", "path": "a.mp3", "sentence": "Merhaba", "locale": "tr"},
        {"client_id": "client-b", "path": "b.mp3", "sentence": "Günaydın", "locale": "tr"},
    ]
    for row in rows:
        (tmp_path / row["path"]).write_bytes(b"synthetic")
    with (tmp_path / "train.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    manifest = select_common_voice(
        tmp_path, limit=2, seed=42, source_version="cv26", split="train"
    )

    assert len(manifest.selected_clips) == 2


def test_common_voice_resolves_standard_clips_subdirectory(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    rows = [
        {"client_id": "client-a", "path": "a.mp3", "sentence": "Merhaba", "locale": "tr"},
        {"client_id": "client-b", "path": "b.mp3", "sentence": "Günaydın", "locale": "tr"},
    ]
    for row in rows:
        (clips / row["path"]).write_bytes(b"synthetic")
    with (tmp_path / "train.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    manifest = select_common_voice(
        tmp_path, limit=2, seed=42, source_version="cv26", split="train"
    )

    assert len(manifest.selected_clips) == 2
    assert all(clip["path"].startswith("clips/") for clip in manifest.selected_clips)
