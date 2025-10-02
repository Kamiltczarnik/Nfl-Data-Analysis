## Conventions

### Scope & File Creation

- Do not create new top-level folders or files without updating `docs/MANIFEST.md` and linking from `Readme`.
- Prefer extending existing modules under `src/*` as documented in `docs/ARCHITECTURE.md`.
- If a file appears missing, first check `requirements.txt` scaffold and `docs/MANIFEST.md`.

### Python Style

- Use black-compatible formatting and flake8-friendly code; type hints on public functions.
- Avoid single-letter variable names. Prefer descriptive names.
- Handle errors explicitly; avoid bare excepts.

### Data & Time-ordering

- All features must be computed as-of prediction time; no peeking beyond target game/week.
- Parquet partitions: `season`, `week`. Keys: `game_id`, `team`, `opponent`.

### Configs & Overrides

- Only modify behavior via `configs/*.yaml` and `overrides/*.yaml`.
- Do not hardcode paths or magic numbers; place in configs.

### Commit Discipline

- One logical change per commit. Update docs and manifest alongside code.


