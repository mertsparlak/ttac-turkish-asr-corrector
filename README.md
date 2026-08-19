# TTAC — Turkish Technical ASR Corrector

This repository contains the Milestone 0 evidence pilot for the Turkish Technical ASR Corrector project. Milestone 0 is training-free: it measures current ASR errors, tests conservative baselines, and produces the evidence needed before any correction model is trained.

## Core development

The core package intentionally has no GPU engine dependency. Install the locked development environment with `uv sync --frozen`, then validate the sample configuration:

```text
uv run ttac config validate --config configs/pilot.yaml
uv run pytest -m "not gpu"
```

The core package owns configuration, stable transcription/evaluation identities, the SQLite job ledger, and the versioned worker protocol. Whisper and Qwen environments are added later under `workers/` and must not be installed into the core environment.

Raw audio, model caches, private participant records, and runtime SQLite state stay outside version control. See the Milestone 0 plan in `docs/plans/` for the complete evidence contract and verification gates.

## Common Voice intake

Download the Turkish **Scripted Speech** release from the official [Mozilla Data Collective Common Voice page](https://commonvoice.mozilla.org/en/datasets). Keep the exact release number; do not use an unpinned “latest” label. After extracting the archive, point `--root` at the directory that directly contains `validated.tsv` and its `clips/` directory. For example:

```powershell
uv run ttac data select-common-voice `
  --root data/common_voice/cv26-tr `
  --output artifacts/pilot/common_voice_selection_cv26.json `
  --limit 100 `
  --seed 42 `
  --source-version cv26 `
  --split train
```

The command writes a deterministic, checksum-bound selection manifest. It pseudonymizes `client_id` values into `spk-*` identifiers and does not copy audio or expose the original client IDs. Keep the downloaded archive and raw audio outside Git; commit only the resulting allowlisted manifest if the project’s release policy permits it.

The sample config intentionally uses `PIN_REQUIRED` for the model revision. Replace it with the immutable revision selected during the resource-gate setup before downloading or running a real model.
