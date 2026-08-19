from ttac.evaluation.terms import TermMention, score_term_mentions


def test_term_metrics_score_surface_canonical_and_suffix_independently() -> None:
    reference = [
        TermMention(
            mention_id="m1",
            utterance_id="u1",
            term_id="pytorch",
            canonical_term="PyTorch",
            surface="PyTorch'ta",
            accepted_aliases=("pay torçta",),
            suffix="ta",
            term_family="pytorch",
            category="framework",
        ),
        TermMention(
            mention_id="m2",
            utterance_id="u1",
            term_id="hugging_face",
            canonical_term="Hugging Face",
            surface="Hugging Face",
            accepted_aliases=(),
            suffix="",
            term_family="hugging_face",
            category="platform",
        ),
    ]
    hypothesis = [
        TermMention(
            mention_id="m1",
            utterance_id="u1",
            term_id="pytorch",
            canonical_term="PyTorch",
            surface="pay torçta",
            accepted_aliases=(),
            suffix="ta",
            term_family="pytorch",
            category="framework",
        ),
        TermMention(
            mention_id="m2",
            utterance_id="u1",
            term_id="hugging_face",
            canonical_term="Hugging Face",
            surface="Hugging Face",
            accepted_aliases=(),
            suffix="ı",
            term_family="hugging_face",
            category="platform",
        ),
    ]

    score = score_term_mentions(reference, hypothesis)
    assert score.total == 2
    assert score.canonical_accuracy == 1.0
    assert score.surface_accuracy == 1.0
    assert score.suffix_preservation == 0.5
