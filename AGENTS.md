# AGENTS.md

## Repository goals

- Agentic project template — standardized structure, tooling, and workflows for building AI Agents.
- Framework-agnostic agent support (e.g. `pydantic-ai`).
- Keep changes small, reviewable, and consistent with existing style.

## High-signal repo map

- `src/`: main source code
  - `agents/`: SDK-agnostic agent definitions and orchestration logic
  - `tools/`: custom tools and functional integrations for agents
  - `prompts/`: system prompts and templates
  - `evals/`: evaluation frameworks and scripts (e.g. Phoenix)
  - `data/`: data download and generation scripts
  - `utils/`: shared utilities (logging, etc.)
- `data/`: project data (raw, interim, processed, external)
- `notebooks/`: Jupyter notebooks (numbered naming convention)
- `tests/`: standard test suite
- `docker/`: Dockerfile and container configuration for agents and Phoenix observability
- `references/`: explanatory materials

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
- **Modern Python (3.11+) Typing**:
  - Prefer built-in collections (`dict`, `list`, `set`, `tuple`, `type`, `collections.abc.Callable`, `collections.abc.AsyncIterator`) over `typing.Dict`, `typing.List`, `typing.Callable`, etc.
  - Use native union syntax `|` instead of `typing.Union` and `typing.Optional`.
  - Use `typing.Self` for class constructors (`from_yaml`, `from_file`), builder methods, and fluent APIs returning instance types.
  - Use PEP 695 `type` syntax for clean type aliases where appropriate.
  - Define structural interfaces using `typing.Protocol`.
- **Leaf Contracts Architecture**:
  - Store protocols, DTOs, and interface definitions in dedicated leaf `contracts/` subpackages (e.g. `src/tools/contracts/`, `src/agents/contracts/`).
  - Leaf contract modules MUST have **zero internal project imports** (importing only from standard library) to eliminate circular dependencies and ensure clean dependency inversion.
- Follow existing typing patterns; avoid introducing new style/tooling unless required.
- Don't reformat unrelated code.
- **Semantic Commits**: Always use semantic commit messages following the Conventional Commits specification.
  - Format: `<type>(<scope>)?(!)?: <description>` (e.g., `feat(auth): add login button` or `fix!: remove legacy API`).
  - Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `revert`.
  - Keep the subject line concise and under 72 characters.

## Validation (run before handoff)

Use the `/precommit` skill to validate changes before committing.

## Pull Requests & Documentation

- Every pull request MUST follow the template structure defined in `.github/pull_request_template.md`.
- Both humans and agents must answer the guiding questions in each section and **MUST NOT** delete the questions themselves (keep them in the final PR description as plain text).
- The `[Answer here]` placeholders must be completely replaced with the actual response details.
- Agents preparing changes or a walkthrough.md must ensure their final summaries align with these sections and answer the questions explicitly:
  - **Summary**: Core goal, current vs new behavior, necessity of change.
  - **Key Changes**: Files modified/added, dependency changes.
  - **Discussion & Pitfalls**: Architectural tradeoffs, security/performance implications, rejected alternatives.
  - **Verification**: Tests run, local manual verification steps.

## Environment & dependency management

- Python: **3.13** (see `pyproject.toml`).
- Package manager: **uv**.
- Install dev dependencies: `uv sync --extra all`.

## Safety & secrets

- Respect `.gitignore` file. Do not access files mentioned in `.gitignore`.
- Never read `.env` file. It's containing secrets.
- Never commit secrets. Treat `.env` as sensitive.
- Never use secrets in exposed forms. If so, notify user that secrets were used openly and suggest to remove them and use tokens instead.
- When you must use a secret, ask user to provide a token instead.
- Never use tokens in a plain form (e.g. embedding tokens in URLs, command arguments, or log messages). Use only `gh auth` and `gh` CLI.
- Before using `gh` commands, ensure the correct GitHub token environment variable is initialized. Refer to the precise command sequences in the [.agents/skills/python-coder/SKILL.md](.agents/skills/python-coder/SKILL.md) runbook. Example:

```bash
export GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' .env | cut -d= -f2- | xargs) && gh run view <RUN_ID>
```


## Docs

- Update docs for every new functionality.
- Update or add architectural diagrams for new code using Mermaid.

## Agent skills

### Issue tracker

Issues are tracked using GitHub Issues via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Uses single-context domain documentation at the repo root. See `docs/agents/domain.md`.
