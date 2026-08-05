# Testing, Linting & Quality Control Guide

This guide covers automated testing with Pytest, code formatting with Ruff, pre-commit git hooks, and PR validation rules.

---

## 1. Running Test Suite (`pytest`)

Execute the full test suite using `uv`:

```bash
uv run pytest
```

### Running Specific Test Modules
```bash
# Run agent framework tests
uv run pytest tests/test_agents/

# Run tool tests
uv run pytest tests/test_tools/

# Run API tests
uv run pytest tests/test_api/
```

---

## 2. Formatting & Linting (`ruff`)

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

## 3. Pre-Commit Validation (`make precommit`)

Before submitting code, run the pre-commit target to execute tests, formatting, and PR validation:

```bash
make precommit
```

---

## 4. Pull Request & Semantic Commit Validation

Pull request descriptions must follow `.github/pull_request_template.md` without leftover default placeholders:

```bash
# Validate PR body description
uv run python -m src.utils.pr_validator --pr-body-file .github/pull_request_template.md

# Validate Conventional Commit message
uv run python -m src.utils.pr_validator --commit-msg "feat(tools): add new weather tool"
```
