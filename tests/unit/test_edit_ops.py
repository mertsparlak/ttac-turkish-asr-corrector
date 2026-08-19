from ttac.evaluation.edit_ops import count_edits, levenshtein_edits


def test_hand_calculated_token_edits_are_deterministic() -> None:
    operations = levenshtein_edits(["a", "b", "c"], ["a", "x", "c", "d"])
    assert count_edits(operations) == {"insertions": 1, "deletions": 0, "substitutions": 1}
    assert [(item.operation, item.reference, item.hypothesis) for item in operations] == [
        ("equal", "a", "a"),
        ("substitute", "b", "x"),
        ("equal", "c", "c"),
        ("insert", None, "d"),
    ]


def test_empty_reference_counts_insertions() -> None:
    operations = levenshtein_edits([], ["bir", "iki"])
    assert count_edits(operations) == {"insertions": 2, "deletions": 0, "substitutions": 0}
