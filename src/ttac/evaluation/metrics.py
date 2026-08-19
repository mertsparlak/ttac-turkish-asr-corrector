"""Raw and Turkish-normalized text metrics plus conservative damage labels."""

from dataclasses import dataclass

from ttac.evaluation.edit_ops import count_edits, levenshtein_edits
from ttac.text.normalize_tr import normalize_tr_for_wer


@dataclass(frozen=True)
class TrackScore:
    reference_length: int
    insertions: int
    deletions: int
    substitutions: int
    wer: float
    cer: float


@dataclass(frozen=True)
class TextScore:
    raw: TrackScore
    normalized: TrackScore


def _rate(errors: int, denominator: int) -> float:
    return 0.0 if denominator == 0 and errors == 0 else (1.0 if denominator == 0 else errors / denominator)


def _track_score(reference: str, hypothesis: str, *, normalized: bool) -> TrackScore:
    if normalized:
        reference = normalize_tr_for_wer(reference)
        hypothesis = normalize_tr_for_wer(hypothesis)
    reference_tokens, hypothesis_tokens = reference.split(), hypothesis.split()
    operations = levenshtein_edits(reference_tokens, hypothesis_tokens)
    counts = count_edits(operations)
    reference_chars, hypothesis_chars = list(reference), list(hypothesis)
    char_counts = count_edits(levenshtein_edits(reference_chars, hypothesis_chars))
    return TrackScore(
        reference_length=len(reference_tokens),
        insertions=counts["insertions"],
        deletions=counts["deletions"],
        substitutions=counts["substitutions"],
        wer=_rate(sum(counts.values()), len(reference_tokens)),
        cer=_rate(sum(char_counts.values()), len(reference_chars)),
    )


def score_text(reference: str, hypothesis: str) -> TextScore:
    return TextScore(
        raw=_track_score(reference, hypothesis, normalized=False),
        normalized=_track_score(reference, hypothesis, normalized=True),
    )


def classify_before_after(reference: str, before: str, after: str) -> str:
    reference_normalized = normalize_tr_for_wer(reference)
    before_normalized = normalize_tr_for_wer(before)
    after_normalized = normalize_tr_for_wer(after)
    if before_normalized != reference_normalized and after_normalized == reference_normalized:
        return "improved"
    if before_normalized == reference_normalized and after_normalized != reference_normalized:
        return "damaged"
    if before_normalized == reference_normalized and after_normalized == reference_normalized:
        if before != reference or after != reference:
            return "orthographic_only"
        return "unchanged"
    return "unchanged"
