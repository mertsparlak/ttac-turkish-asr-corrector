import json
from pathlib import Path

from ttac.text.normalize_tr import normalize_tr, normalize_tr_for_wer


def test_turkish_normalizer_matches_golden_cases() -> None:
    cases = json.loads(
        Path("tests/fixtures/metrics/golden_normalization.json").read_text(encoding="utf-8")
    )
    for case in cases:
        assert normalize_tr(case["raw"]) == case["normalized"]


def test_wer_track_removes_sentence_punctuation_but_keeps_term_punctuation() -> None:
    assert normalize_tr_for_wer("Merhaba, dünya! Qwen3.5-v2") == "merhaba dünya qwen3.5-v2"
