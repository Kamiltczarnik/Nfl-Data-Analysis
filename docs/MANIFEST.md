## Repository Manifest (Authoritative)

This manifest enumerates intended files and their purpose. New agents must consult this before creating files.

### Top-level

- `Readme` — project plan and sprints
- `requirements.txt` — deps
- `configs/` — YAML configs (`paths.yaml`, `features.yaml`)
- `overrides/` — manual YAML overrides (keep `.gitkeep`)
- `data/` — parquet lake and snapshots (gitignored)
- `models/` — saved model artifacts
- `src/` — source code modules
- `docs/` — documentation (`ARCHITECTURE.md`, `CONVENTIONS.md`, this file)

### src layout

- `src/data/readers.py` — nflreadpy wrappers (no API changes without docs)
- `src/data/transforms.py` — cleaning, IDs, drives
- `src/data/overrides.py` — apply manual overrides
- `src/features/*.py` — rolling, strategy, qb, trenches, situational, assemble
- `src/models/*.py` — baseline, gbm, stack, calibrate
- `src/eval/*.py` — metrics, backtest, ablations
- `src/serve/*.py` — predict, explain

### Non-goals (do not add without explicit scope change)

- Web UI/server; cloud infra code; heavy scraping beyond ESPN PBWR/PRWR optional tables
- Live in-game model (unless explicitly greenlit)


