from pathlib import Path

import pytest

from ttac.config import ConfigError, load_config


def test_load_config_validates_required_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "pilot.yaml"
    config_path.write_text(
        """
seed: 42
ledger_path: runtime/pilot.sqlite3
artifact_dir: artifacts/pilot
source_root: data/common_voice
engine: whisper_small
model_repository: openai/whisper-small
model_revision: abc123
normalizer_version: tr-v1
decoding:
  language: tr
  temperature: 0
""".lstrip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.seed == 42
    assert config.engine == "whisper_small"
    assert config.decoding == {"language": "tr", "temperature": 0}
    assert config.ledger_path == (tmp_path / "runtime/pilot.sqlite3").resolve()
    assert config.artifact_dir == (tmp_path / "artifacts/pilot").resolve()


def test_load_config_rejects_missing_required_field(tmp_path: Path) -> None:
    config_path = tmp_path / "pilot.yaml"
    config_path.write_text("seed: 42\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="model_repository"):
        load_config(config_path)


def test_load_config_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    config_path = tmp_path / "pilot.yaml"
    config_path.write_text(
        """
seed: 42
ledger_path: runtime/pilot.sqlite3
artifact_dir: artifacts/pilot
engine: fake
model_repository: fixture/fake
model_revision: fixture-v1
normalizer_version: tr-v1
unexpected: true
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unexpected"):
        load_config(config_path)
