# Testing, Linting & Quality Control Guide

This guide covers the quality assurance stack, automated test suites, code linters, security scanners, and pre-commit git hooks configured in the repository.

---

## 1. Quality Assurance Tools & Verification Matrix

The repository enforces strict code quality, type safety, documentation standards, and security checks across Python, Markdown, SQL, YAML, and TypeScript/Svelte files.

| Tool Name | Target Files | Purpose & Why It Is Needed | Manual Command |
| :--- | :--- | :--- | :--- |
| **`Ruff Format`** | `*.py` | Fast Python code auto-formatter ensuring consistent PEP 8 formatting (line length 100). | `uv run ruff format .` |
| **`Ruff Check`** | `*.py` | Fast Python linter detecting unused imports, syntax errors, and code style issues. | `uv run ruff check .` |
| **`Ty Type Check`** | `*.py` | Static type checker validating type annotations and preventing type mismatches. | `uv run ty check .` |
| **`Bandit Security Check`** | `*.py` | Security linter analyzing Python code for security vulnerabilities (e.g. unsafe exec, weak hashes). | `uv run bandit -r src/` |
| **`Pymarkdown Scan`** | `*.md` | Markdown linter validating header hierarchy, code block language tags, and formatting rules. | `uv run pymarkdown scan docs/ README.md` |
| **`SQLFluff`** | `*.sql` | SQL linter and auto-formatter ensuring standard SQL dialect formatting. | `uv run sqlfluff lint` |
| **`Pytest Suite`** | `tests/**/*.py` | Runs automated unit and integration tests across agents, tools, API endpoints, and utilities. | `uv run pytest` |
| **`Semgrep Scan`** | `*.py`, `*.yaml` | Static analysis scanner checking custom security rules (`.semgrep/rules.yaml`) for secret leaks. | `uv run semgrep scan` |
| **`Yamllint Scan`** | `*.yaml`, `*.yml` | Linter validating YAML syntax, indentation, and key formatting (`configs/agent_config.yaml`). | `uv run yamllint .` |
| **`Frontend Lint & Type Check`** | `frontend/src/*` | Svelte compiler and TypeScript check (`svelte-check`) verifying UI components and reactive state. | `npm run check --prefix frontend` |
| **`Frontend Format (Prettier)`** | `frontend/src/*` | Formatter ensuring clean formatting for Svelte components, HTML, CSS, and TypeScript. | `npm run format --prefix frontend` |
| **`Mutmut Mutation Testing`** | `src/utils/*.py`, `src/tools/text_extractor.py`, `src/agents/config.py` | Injects synthetic mutations to assess test suite effectiveness and catch untested logic branches. | `make mutate` |
| **`Check Commit Message`** | Git Commits | Validates Conventional Commit message format (`<type>(<scope>): <description>`) with max 72 chars. | Automatic on `git commit` |

---

## 2. Running the Test Suite (`pytest`)

Execute the full test suite using `uv`:

```bash
uv run pytest
```

### Running Specific Test Modules
```bash
# Run agent framework tests
uv run pytest tests/test_agents.py

# Run tool tests
uv run pytest tests/test_tools_factory.py

# Run API tests
uv run pytest tests/test_api.py
```

---

## 3. Formatting & Linting (`ruff`)

Ruff enforces Python 3.13 style standards and line length limits (100 characters).

### Run Linter Checks
```bash
uv run ruff check .
```

### Automatically Fix Linting Errors
```bash
uv run ruff check --fix .
```

### Format Codebase
```bash
uv run ruff format .
```

---

## 4. Pre-Commit Validation (`make precommit`)

Before submitting code, run the pre-commit target to execute all checks across all files:

```bash
make precommit
```

Or install pre-commit hooks locally to run automatically on every commit:

```bash
uv run pre-commit install
```

---

## 5. Pull Request & Semantic Commit Validation

Pull request descriptions must follow `.github/pull_request_template.md` without leftover default placeholders:

```bash
# Validate PR body description
uv run python -m src.utils.pr_validator --pr-body-file .github/pull_request_template.md

# Validate Conventional Commit message
uv run python -m src.utils.pr_validator --commit-msg "feat(tools): add new weather tool"
```

---

## 6. Mutation Testing (`make mutate`)

Mutation testing with `mutmut` evaluates test quality by introducing synthetic bugs (mutants) into source files (`src/utils/retry.py`, `src/utils/pr_validator.py`, `src/tools/text_extractor.py`, `src/agents/config.py`) and running target pytest suites (`tests/test_retry.py`, `tests/test_pr_validator.py`, `tests/test_text_extractor.py`, `tests/test_phoenix_config.py`).

### Executing Mutation Testing
```bash
make mutate
```

### Relationship to Pytest & Pre-Commit
- **Pytest Integration**: `mutmut` invokes `pytest` under the hood for each mutant with targeted test selection (`pytest_add_cli_args_test_selection`) and disables slow telemetry/coverage plugins (`-p no:cov -p no:logfire`) for fast feedback.
- **Pre-Commit Separation**: Because mutation testing evaluates hundreds of mutants and takes several minutes, `make mutate` is kept separate from the fast `make precommit` git hook pipeline.

For detailed configuration, interactive TUI browsing, and mutant suppression pragmas, see [Mutation Testing Guide](../mutation_testing.md).

