---
name: precommit
description: Ensure that the code is linted, tested, and secure before committing.
---

Use this skill to validate code before committing. Run checks only on new or changed files to save time. Use the local `.venv` for Python-based tools.

## Changed files helper

Define the changed file list from both unstaged and staged changes:

```bash
changed_files="$( (git diff --name-only --diff-filter=ACMR; git diff --name-only --diff-filter=ACMR --staged) | sort -u )"
```

## Linting

Run Python linters only on changed Python files:

```bash
python_files="$(printf '%s\n' "$changed_files" | grep -iE '\.py$' || true)"
if [ -n "$python_files" ]; then
  .venv/bin/ruff format -- $python_files
  .venv/bin/ruff check -- $python_files
fi
```

Run Markdown linting only on changed Markdown files:

```bash
md_files="$(printf '%s\n' "$changed_files" | grep -iE '\.md$' || true)"
if [ -n "$md_files" ]; then
  .venv/bin/pymarkdown --disable-rules MD007,MD013,MD024,MD033 scan -- $md_files
fi
```

## Testing

Run tests only for changed test files:

```bash
test_files="$(printf '%s\n' "$changed_files" | grep -iE '(^|/)test_.*\.py$|_test\.py$' || true)"
if [ -n "$test_files" ]; then
  .venv/bin/python -m pytest -v -- $test_files
fi
```

## Security checks

Run Bandit only on changed Python files:

```bash
if [ -n "$python_files" ]; then
  .venv/bin/bandit -c pyproject.toml -- $python_files
fi
```

## Recommended quick sequence

```bash
changed_files="$( (git diff --name-only --diff-filter=ACMR; git diff --name-only --diff-filter=ACMR --staged) | sort -u )"
python_files="$(printf '%s\n' "$changed_files" | grep -iE '\.py$' || true)"
md_files="$(printf '%s\n' "$changed_files" | grep -iE '\.md$' || true)"
test_files="$(printf '%s\n' "$changed_files" | grep -iE '(^|/)test_.*\.py$|_test\.py$' || true)"

if [ -n "$python_files" ]; then
  .venv/bin/ruff format -- $python_files
  .venv/bin/ruff check -- $python_files
  .venv/bin/bandit -c pyproject.toml -- $python_files
fi

if [ -n "$md_files" ]; then
  .venv/bin/pymarkdown --disable-rules MD007,MD013,MD024,MD033 scan -- $md_files
fi

if [ -n "$test_files" ]; then
  .venv/bin/python -m pytest -v -- $test_files
fi
```

These steps are intentionally compact so they can be run individually or in CI.
