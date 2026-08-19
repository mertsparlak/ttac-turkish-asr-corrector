"""Mention-level technical term scoring from explicit annotations."""

from dataclasses import dataclass

from ttac.text.normalize_tr import normalize_tr_for_wer


@dataclass(frozen=True)
class TermMention:
    mention_id: str
    utterance_id: str
    term_id: str
    canonical_term: str
    surface: str
    accepted_aliases: tuple[str, ...] = ()
    suffix: str = ""
    term_family: str = ""
    category: str = ""
    surface_start: int = 0
    surface_end: int = 0
    multi_token: bool = False
    version: str | None = None


@dataclass(frozen=True)
class TermMetrics:
    total: int
    surface_correct: int
    canonical_correct: int
    suffix_preserved: int
    identity_damage: int

    @property
    def surface_accuracy(self) -> float:
        return self.surface_correct / self.total if self.total else 0.0

    @property
    def canonical_accuracy(self) -> float:
        return self.canonical_correct / self.total if self.total else 0.0

    @property
    def suffix_preservation(self) -> float:
        return self.suffix_preserved / self.total if self.total else 0.0


def score_term_mentions(
    reference: list[TermMention], hypothesis: list[TermMention]
) -> TermMetrics:
    by_id = {mention.mention_id: mention for mention in hypothesis}
    surface_correct = canonical_correct = suffix_preserved = identity_damage = 0
    for expected in reference:
        actual = by_id.get(expected.mention_id)
        if actual is None:
            identity_damage += 1
            continue
        canonical_ok = actual.term_id == expected.term_id
        accepted_surfaces = (expected.surface, *expected.accepted_aliases)
        surface_ok = normalize_tr_for_wer(actual.surface) in {
            normalize_tr_for_wer(surface) for surface in accepted_surfaces
        }
        suffix_ok = normalize_tr_for_wer(actual.suffix) == normalize_tr_for_wer(expected.suffix)
        surface_correct += surface_ok
        canonical_correct += canonical_ok
        suffix_preserved += suffix_ok
        identity_damage += not canonical_ok
    return TermMetrics(
        total=len(reference),
        surface_correct=surface_correct,
        canonical_correct=canonical_correct,
        suffix_preserved=suffix_preserved,
        identity_damage=identity_damage,
    )
