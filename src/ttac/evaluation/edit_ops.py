"""Deterministic Levenshtein edit operations."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EditOp:
    operation: str
    reference: str | None
    hypothesis: str | None
    reference_index: int
    hypothesis_index: int


def levenshtein_edits(reference: Sequence[str], hypothesis: Sequence[str]) -> list[EditOp]:
    rows, columns = len(reference), len(hypothesis)
    distance = [[0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(rows + 1):
        distance[row][0] = row
    for column in range(columns + 1):
        distance[0][column] = column
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            substitution = distance[row - 1][column - 1] + (reference[row - 1] != hypothesis[column - 1])
            deletion = distance[row - 1][column] + 1
            insertion = distance[row][column - 1] + 1
            distance[row][column] = min(substitution, deletion, insertion)

    operations: list[EditOp] = []
    row, column = 0, 0
    while row < rows or column < columns:
        if row < rows and column < columns and reference[row] == hypothesis[column]:
            operations.append(EditOp("equal", reference[row], hypothesis[column], row, column))
            row += 1
            column += 1
            continue
        if row < rows and column < columns:
            substitution_cost = distance[row + 1][column + 1] - distance[row][column]
            if substitution_cost == 1:
                operations.append(EditOp("substitute", reference[row], hypothesis[column], row, column))
                row += 1
                column += 1
                continue
        if row < rows and distance[row + 1][column] == distance[row][column] + 1:
            operations.append(EditOp("delete", reference[row], None, row, column))
            row += 1
            continue
        operations.append(EditOp("insert", None, hypothesis[column], row, column))
        column += 1
    return operations


def count_edits(operations: Sequence[EditOp]) -> dict[str, int]:
    return {
        "insertions": sum(item.operation == "insert" for item in operations),
        "deletions": sum(item.operation == "delete" for item in operations),
        "substitutions": sum(item.operation == "substitute" for item in operations),
    }
