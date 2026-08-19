from pathlib import Path

import pytest

from ttac.data.benchmark import (
    FreezeError,
    freeze_content,
    load_benchmark_pack,
    verify_frozen_content,
)

PACK_ROOT = Path("benchmarks/ttac-tech-smoke")


def test_technical_pack_has_frozen_split_and_negative_controls() -> None:
    pack = load_benchmark_pack(PACK_ROOT)

    assert len(pack.read_sentences) == 120
    assert len([row for row in pack.read_sentences if row["split"] == "tech_dev"]) == 80
    frozen = [row for row in pack.read_sentences if row["split"] == "tech_test_frozen"]
    assert len(frozen) == 40
    assert sum(row["negative_control"] for row in frozen) >= 8
    assert len(pack.spontaneous_prompts) == 12
    assert set(pack.term_families_by_split["tech_dev"]).isdisjoint(
        pack.term_families_by_split["tech_test_frozen"]
    )
    assert len(pack.operational_lexicon) == 12
    assert all(row["frozen_before_authoring"] for row in pack.operational_lexicon)


def test_benchmark_freeze_rejects_in_place_change(tmp_path: Path) -> None:
    source = tmp_path / "pack"
    source.mkdir()
    (source / "sentences.tsv").write_text("sentence_id\tsplit\nutt-1\ttech_dev\n", encoding="utf-8")
    (source / "terms.tsv").write_text("term_id\tterm_family\nterm-1\tfamily-1\n", encoding="utf-8")

    manifest = freeze_content(source, content_version="v1", stage="pre_recording")
    verify_frozen_content(source, manifest)
    (source / "sentences.tsv").write_text("sentence_id\tsplit\nutt-1\ttech_test_frozen\n", encoding="utf-8")

    with pytest.raises(FreezeError, match="new content version"):
        verify_frozen_content(source, manifest)
