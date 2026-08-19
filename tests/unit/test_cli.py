import csv
import json
from pathlib import Path

from ttac.cli import main


def test_cli_validates_config_and_prints_machine_readable_summary(
    tmp_path: Path, capsys
) -> None:
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
""".lstrip(),
        encoding="utf-8",
    )

    assert main(["config", "validate", "--config", str(config_path)]) == 0

    output = capsys.readouterr().out
    assert '"engine": "fake"' in output
    assert '"seed": 42' in output


def test_cli_selects_common_voice_and_writes_manifest(tmp_path: Path, capsys) -> None:
    root = tmp_path / "cv"
    root.mkdir()
    rows = [
        {"client_id": "client-a", "path": "a.mp3", "sentence": "Merhaba", "locale": "tr", "split": "train"},
        {"client_id": "client-b", "path": "b.mp3", "sentence": "Günaydın", "locale": "tr", "split": "train"},
    ]
    for row in rows:
        (root / row["path"]).write_bytes(row["client_id"].encode())
    with (root / "validated.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    output = tmp_path / "selection.json"

    assert main(
        [
            "data",
            "select-common-voice",
            "--root",
            str(root),
            "--output",
            str(output),
            "--limit",
            "2",
            "--seed",
            "42",
            "--source-version",
            "cv26",
            "--split",
            "train",
        ]
    ) == 0

    assert json.loads(output.read_text(encoding="utf-8"))["source_version"] == "cv26"
    assert "selection manifest" in capsys.readouterr().out
