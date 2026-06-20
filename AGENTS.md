# AGENTS.md

## Repository goals

- Data Science project template — standardized structure, tooling, and workflows for DS projects.
- Keep changes small, reviewable, and consistent with existing style.

## High-signal repo map

- `src/`: main source code
  - `data/`: data download and generation scripts
  - `features/`: raw data to features transformation
  - `models/`: model training and prediction scripts
  - `visualization/`: EDA and results visualizations
  - `utils/`: shared utilities (logging, etc.)
- `data/`: project data (raw, interim, processed, external)
- `models/`: trained and serialized models
- `notebooks/`: Jupyter notebooks (numbered naming convention)
- `tests/`: test suite
- `docker/`: Dockerfile and container configuration
- `reports/figures/`: generated graphics and figures
- `references/`: data dictionaries and explanatory materials

## Coding style

- Prefer fixing root causes over adding workarounds.

## Code execution

- Do not access files beyond current location.
- Execute Python commands only with local `.venv` environment.

## Tests

- Write tests for each functionality created. Prefer adding full testing suite over adding small single tests.
- Add/adjust tests close to the code you changed (typically under `tests/`).
- If you only changed a small area, it's ok to run a narrower `pytest` selection first, but still run the full validation before handing off.

## Style & conventions

- Formatting/linting is enforced via `ruff` (line length 100, target py313).
- Follow existing typing patterns; avoid introducing new style/tooling unless required.
- Don't reformat unrelated code.

## Validation (run before handoff)

Use the `/precommit` skill to validate changes before committing.

## Environment & dependency management

- Python: **3.13** (see `pyproject.toml`).
- Package manager: **uv**.
- Install dev dependencies: `uv sync --extra all`.

## Safety & secrets

- Respect `.gitignore` file. Do not access files mentioned in `.gitignore`.
- Never commit secrets. Treat `.env` as sensitive.
