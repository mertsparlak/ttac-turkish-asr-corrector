from ttac.evaluation.metrics import classify_before_after, score_text


def test_hand_calculated_raw_and_normalized_wer_cer() -> None:
    score = score_text("a b c", "a x c d")
    assert score.raw.insertions == 1
    assert score.raw.deletions == 0
    assert score.raw.substitutions == 1
    assert score.raw.wer == 2 / 3
    assert score.normalized.wer == 2 / 3
    assert score.raw.cer > 0


def test_orthographic_only_and_damage_statuses_use_normalized_track() -> None:
    assert classify_before_after("Merhaba dünya", "Merhaba, dünya", "Merhaba dünya") == "orthographic_only"
    assert classify_before_after("PyTorch ile eğitim", "başka eğitim", "PyTorch ile eğitim") == "improved"
    assert classify_before_after("PyTorch ile eğitim", "PyTorch ile eğitim", "başka eğitim") == "damaged"
    assert classify_before_after("PyTorch ile eğitim", "başka eğitim", "başka eğitim") == "unchanged"
