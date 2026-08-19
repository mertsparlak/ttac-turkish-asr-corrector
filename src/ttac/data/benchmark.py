"""Technical benchmark loading, split validation, and content freezes."""

from dataclasses import dataclass
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


class FreezeError(RuntimeError):
    """Raised when an immutable content version changes in place."""


@dataclass(frozen=True)
class BenchmarkPack:
    terms: list[dict[str, str]]
    operational_lexicon: list[dict[str, Any]]
    read_sentences: list[dict[str, Any]]
    spontaneous_prompts: list[dict[str, str]]
    term_families_by_split: dict[str, set[str]]


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _bool(value: str | None) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes"}


def load_benchmark_pack(root: str | Path) -> BenchmarkPack:
    pack_root = Path(root).expanduser().resolve()
    terms = _read_tsv(pack_root / "terms.tsv")
    operational_lexicon_raw = _read_tsv(pack_root / "operational_lexicon.tsv")
    sentences_raw = _read_tsv(pack_root / "sentences.tsv")
    prompts = _read_tsv(pack_root / "spontaneous_prompts.tsv")
    if not terms or not operational_lexicon_raw or not sentences_raw or not prompts:
        raise ValueError("benchmark pack files must not be empty")
    operational_lexicon: list[dict[str, Any]] = []
    term_names = {row.get("canonical_term", "") for row in terms}
    for row in operational_lexicon_raw:
        if not row.get("canonical_term") or row["canonical_term"] not in term_names:
            raise ValueError("operational lexicon contains an unknown canonical term")
        if not row.get("source_id") or not row.get("source_uri"):
            raise ValueError("operational lexicon rows require source receipts")
        if not _bool(row.get("frozen_before_authoring")):
            raise ValueError("operational lexicon must be frozen before authoring")
        lex_item: dict[str, Any] = dict(row)
        lex_item["frozen_before_authoring"] = True
        operational_lexicon.append(lex_item)
    term_families = {row["term_id"]: row["term_family"] for row in terms}
    sentences: list[dict[str, Any]] = []
    families_by_split: dict[str, set[str]] = {"tech_dev": set(), "tech_test_frozen": set()}
    for row in sentences_raw:
        split = row.get("split", "")
        if split not in families_by_split:
            raise ValueError(f"unsupported benchmark split: {split}")
        term_family = row.get("term_family", "")
        term_id = row.get("term_id", "")
        if term_id and term_id in term_families and term_families[term_id] != term_family:
            raise ValueError(f"term family mismatch for {term_id}")
        if term_family:
            families_by_split[split].add(term_family)
        sentence_item: dict[str, Any] = dict(row)
        sentence_item["negative_control"] = _bool(row.get("negative_control"))
        sentences.append(sentence_item)
    if families_by_split["tech_dev"] & families_by_split["tech_test_frozen"]:
        overlap = sorted(families_by_split["tech_dev"] & families_by_split["tech_test_frozen"])
        raise ValueError(f"term families leak across benchmark splits: {', '.join(overlap)}")
    return BenchmarkPack(terms, operational_lexicon, sentences, prompts, families_by_split)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _file_checksums(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.name.startswith(".")
    }


def freeze_content(root: str | Path, *, content_version: str, stage: str) -> dict[str, Any]:
    if not content_version or stage not in {"pre_recording", "release"}:
        raise ValueError("content_version and a supported freeze stage are required")
    pack_root = Path(root).expanduser().resolve()
    files = _file_checksums(pack_root)
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":"))
    content_id = f"content-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]}"
    return {
        "schema_version": "ttac-benchmark-freeze/v1",
        "content_version": content_version,
        "stage": stage,
        "content_id": content_id,
        "files": files,
    }


def verify_frozen_content(root: str | Path, manifest: dict[str, Any]) -> None:
    current = _file_checksums(Path(root).expanduser().resolve())
    if current != manifest.get("files"):
        raise FreezeError("benchmark changed in place; create a new content version")
