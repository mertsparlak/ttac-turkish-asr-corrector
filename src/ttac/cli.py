"""Thin command-line entry point for the TTAC core package."""

import argparse
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from ttac import __version__
from ttac.config import ConfigError, load_config
from ttac.data.common_voice import select_common_voice


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ttac", description="TTAC evidence pilot tools")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    config_parser = subparsers.add_parser("config", help="configuration operations")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    validate = config_subparsers.add_parser("validate", help="validate a pilot YAML file")
    validate.add_argument("--config", required=True, type=Path)
    data_parser = subparsers.add_parser("data", help="data intake operations")
    data_subparsers = data_parser.add_subparsers(dest="data_command", required=True)
    select = data_subparsers.add_parser(
        "select-common-voice", help="create a deterministic Common Voice selection manifest"
    )
    select.add_argument("--root", required=True, type=Path)
    select.add_argument("--output", required=True, type=Path)
    select.add_argument("--limit", required=True, type=int)
    select.add_argument("--seed", required=True, type=int)
    select.add_argument("--source-version", required=True)
    select.add_argument("--split", default=None)
    return parser


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "config" and args.config_command == "validate":
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"configuration error: {exc}", file=sys.stderr)
            return 2
        values = asdict(config)
        for key, value in values.items():
            if isinstance(value, Path):
                values[key] = value.as_posix()
        print(json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.command == "data" and args.data_command == "select-common-voice":
        try:
            manifest = select_common_voice(
                args.root,
                limit=args.limit,
                seed=args.seed,
                source_version=args.source_version,
                split=args.split,
            )
            _write_json_atomic(args.output, manifest.to_dict())
        except (FileNotFoundError, ValueError, OSError) as exc:
            print(f"Common Voice selection error: {exc}", file=sys.stderr)
            return 2
        print(f"selection manifest: {args.output.expanduser().resolve()}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
