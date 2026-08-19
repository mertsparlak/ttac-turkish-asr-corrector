"""Conservative recording/reference quality checks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QCResult:
    status: str
    reasons: list[str]
    pronunciation_variant: bool = False


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def qc_read_recording(
    *,
    reference: str,
    observed: str,
    audio_exists: bool,
    consent_status: str,
    pronunciation_variant: bool = False,
    pronunciation_clear: bool = False,
    clipping: bool = False,
    corruption: bool = False,
    artificial_spelling: bool = False,
) -> QCResult:
    reasons: list[str] = []
    if not audio_exists:
        reasons.append("missing_audio")
    if consent_status != "active":
        reasons.append("missing_consent")
    if clipping:
        reasons.append("clipping")
    if corruption:
        reasons.append("corruption")
    if artificial_spelling:
        reasons.append("artificial_spelling")
    same_text = _normalized(reference) == _normalized(observed)
    valid_variant = pronunciation_variant and pronunciation_clear and not artificial_spelling
    if not same_text and not valid_variant:
        reasons.append("content_mismatch")
    return QCResult("passed" if not reasons else "failed", reasons, valid_variant)


def qc_spontaneous_recording(
    *, prompt: str, manual_reference: str | None, audio_exists: bool, consent_status: str
) -> QCResult:
    reasons: list[str] = []
    if not audio_exists:
        reasons.append("missing_audio")
    if consent_status != "active":
        reasons.append("missing_consent")
    if not manual_reference or not manual_reference.strip():
        reasons.append("missing_manual_reference")
    return QCResult("passed" if not reasons else "failed", reasons)
