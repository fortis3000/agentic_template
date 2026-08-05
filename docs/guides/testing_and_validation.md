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
