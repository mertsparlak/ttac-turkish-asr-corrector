"""Validated configuration for the core TTAC pilot."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


class ConfigError(ValueError):
    """Raised when a pilot configuration is missing or malformed."""


@dataclass(frozen=True)
class PilotConfig:
    seed: int
    ledger_path: Path
    artifact_dir: Path
    engine: str
    model_repository: str
    model_revision: str
    normalizer_version: str
    source_root: Path | None = None
    decoding: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.decoding is None:
            object.__setattr__(self, "decoding", {})


_REQUIRED_FIELDS = {
    "seed",
    "ledger_path",
    "artifact_dir",
    "engine",
    "model_repository",
    "model_revision",
    "normalizer_version",
}
_OPTIONAL_FIELDS = {"source_root", "decoding"}


def _path_from_config(value: Any, config_path: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("path values must be non-empty strings")
    path = Path(value).expanduser()
    return (config_path.parent / path).resolve() if not path.is_absolute() else path.resolve()


def load_config(path: str | Path) -> PilotConfig:
    """Load and validate a YAML pilot configuration."""

    config_path = Path(path).expanduser().resolve()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"configuration file does not exist: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be a mapping")
    unknown = set(raw) - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
    if unknown:
        raise ConfigError(f"unknown configuration fields: {', '.join(sorted(unknown))}")
    missing = _REQUIRED_FIELDS - set(raw)
    if missing:
        raise ConfigError(f"missing required configuration fields: {', '.join(sorted(missing))}")
    if not isinstance(raw["seed"], int) or isinstance(raw["seed"], bool):
        raise ConfigError("seed must be an integer")
    if not isinstance(raw.get("decoding"), (dict, type(None))):
        raise ConfigError("decoding must be a mapping")

    string_fields = (
        "engine",
        "model_repository",
        "model_revision",
        "normalizer_version",
    )
    for field in string_fields:
        if not isinstance(raw[field], str) or not raw[field].strip():
            raise ConfigError(f"{field} must be a non-empty string")

    return PilotConfig(
        seed=raw["seed"],
        ledger_path=_path_from_config(raw["ledger_path"], config_path),
        artifact_dir=_path_from_config(raw["artifact_dir"], config_path),
        source_root=(
            _path_from_config(raw["source_root"], config_path)
            if raw.get("source_root") is not None
            else None
        ),
        engine=raw["engine"],
        model_repository=raw["model_repository"],
        model_revision=raw["model_revision"],
        normalizer_version=raw["normalizer_version"],
        decoding=dict(raw.get("decoding") or {}),
    )
