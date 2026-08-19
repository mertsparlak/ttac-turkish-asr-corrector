"""Conservative Turkish normalization with separate WER presentation track."""

import re
import unicodedata

NORMALIZER_VERSION = "tr-v1"
_TURKISH_CASE = str.maketrans("Iİ", "ıi")
_PUNCTUATION_TO_SPACE = re.compile(r"[,;:!?()[\]{}\"“”…]+")


def normalize_tr(text: str) -> str:
    """Normalize Unicode, Turkish casing, punctuation variants, and whitespace."""

    value = unicodedata.normalize("NFKC", text)
    value = value.translate(str.maketrans("’‘–—‐\u00a0", "''--- "))
    value = value.translate(_TURKISH_CASE).lower()
    return " ".join(value.split())


def normalize_tr_for_wer(text: str) -> str:
    """Normalize text for lexical WER while retaining term dots, hyphens, and apostrophes."""

    value = normalize_tr(text)
    return " ".join(_PUNCTUATION_TO_SPACE.sub(" ", value).split())
