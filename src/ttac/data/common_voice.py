"""Deterministic, public-safe Common Voice manifest selection."""

from dataclasses import dataclass
import csv
import hashlib
import json
from pathlib import Path
import random
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


@dataclass(frozen=True)
class SelectionManifest:
    source_version: str
    metadata_checksum: str
    seed: int
    filters: dict[str, Any]
    selected_clips: list[dict[str, str]]
    speaker_distribution: dict[str, int]
    source_checksums: dict[str, str]
    replacement_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "ttac-common-voice-selection/v1",
            "source_version": self.source_version,
            "metadata_checksum": self.metadata_checksum,
            "seed": self.seed,
            "filters": self.filters,
            "selected_clips": self.selected_clips,
            "speaker_distribution": self.speaker_distribution,
            "source_checksums": self.source_checksums,
            "replacement_policy": self.replacement_policy,
        }


def _speaker_id(client_id: str, source_version: str) -> str:
    digest = hashlib.sha256(f"{source_version}|{client_id}".encode("utf-8")).hexdigest()
    return f"spk-{digest[:16]}"


def _metadata_path(dataset_root: Path, split: str | None = None) -> Path:
    candidates = []
    if split:
        candidates.append(dataset_root / f"{split}.tsv")
    candidates.extend((dataset_root / "validated.tsv", dataset_root / "metadata.tsv"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Common Voice metadata file not found")


def select_common_voice(
    root: str | Path,
    *,
    limit: int,
    seed: int,
    source_version: str,
    split: str | None = None,
) -> SelectionManifest:
    # The production pilot is configured for 100–250 clips.  The selector
    # itself also accepts smaller positive limits so tiny offline fixtures can
    # exercise the exact same deterministic path in unit tests.
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not source_version:
        raise ValueError("source_version must be non-empty")
    dataset_root = Path(root).expanduser().resolve()
    metadata_path = _metadata_path(dataset_root, split)

    with metadata_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    candidates: list[tuple[dict[str, str], Path, str]] = []
    missing = 0
    for row in rows:
        if row.get("locale", "tr") != "tr":
            continue
        if split is not None and row.get("split") and row["split"] != split:
            continue
        relative_path = row.get("path", "").strip()
        client_id = row.get("client_id", "").strip()
        if not relative_path or not client_id:
            continue
        relative_audio = Path(relative_path)
        audio_path = (dataset_root / relative_audio).resolve()
        manifest_path = relative_audio
        if not audio_path.exists():
            clips_audio_path = (dataset_root / "clips" / relative_audio).resolve()
            if clips_audio_path.exists():
                audio_path = clips_audio_path
                manifest_path = Path("clips") / relative_audio
        if dataset_root not in audio_path.parents:
            raise ValueError("audio path escapes the dataset root")
        if not audio_path.exists():
            missing += 1
            continue
        clip_id = relative_audio.stem
        row_for_manifest = dict(row)
        row_for_manifest["path"] = manifest_path.as_posix()
        candidates.append((row_for_manifest, audio_path, clip_id))

    candidates.sort(key=lambda item: item[2])
    random.Random(seed).shuffle(candidates)
    selected = candidates[:limit]
    selected_clips: list[dict[str, str]] = []
    source_checksums: dict[str, str] = {}
    distribution: dict[str, int] = {}
    for row, audio_path, clip_id in selected:
        speaker_id = _speaker_id(row["client_id"], source_version)
        selected_clips.append(
            {
                "clip_id": clip_id,
                "path": Path(row["path"]).as_posix(),
                "sentence": row.get("sentence", ""),
                "speaker_id": speaker_id,
            }
        )
        source_checksums[clip_id] = _sha256(audio_path)
        distribution[speaker_id] = distribution.get(speaker_id, 0) + 1

    return SelectionManifest(
        source_version=source_version,
        metadata_checksum=_sha256(metadata_path),
        seed=seed,
        filters={"locale": "tr", "split": split, "limit": limit},
        selected_clips=selected_clips,
        speaker_distribution=distribution,
        source_checksums=source_checksums,
        replacement_policy={"missing_source": "excluded", "missing_count": missing},
    )


def verify_selection_manifest(root: str | Path, manifest: SelectionManifest) -> None:
    """Ensure source metadata and selected audio still match an intake receipt."""

    dataset_root = Path(root).expanduser().resolve()
    metadata_path = _metadata_path(dataset_root, manifest.filters.get("split"))
    if _sha256(metadata_path) != manifest.metadata_checksum:
        raise ValueError("metadata checksum changed; create a new selection manifest")
    for clip in manifest.selected_clips:
        relative = clip.get("path", "")
        audio_path = (dataset_root / relative).resolve()
        if dataset_root not in audio_path.parents or not audio_path.exists():
            raise ValueError(f"selected source is unavailable: {relative}")
        clip_id = clip.get("clip_id", "")
        expected = manifest.source_checksums.get(clip_id)
        if expected != _sha256(audio_path):
            raise ValueError(f"source checksum changed for clip: {clip_id}")
