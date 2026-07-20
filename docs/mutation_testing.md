# Mutation Testing with mutmut

Mutation testing is a technique to assess the quality of your test suite. It works by injecting small bugs (mutations) into your source code and running your tests. If the tests fail, the mutant is **killed** (good). If the tests pass, the mutant **survived** (indicates a testing gap).

---

## 1. Quick Start

To run mutation testing on the pre-configured target modules, simply execute:

```bash
make mutate
```

This runs `mutmut` inside Python's optimized mode (`-O`) to bypass standard package naming assertions and limit runs to the targeted modules.

---

## 2. Interactive Browser (TUI)

You can explore mutations, see the diff of injected bugs, and retest them interactively:

```bash
uv run mutmut browse
```

This starts a terminal-based user interface showing all mutants, their statuses, and allowing you to drill down into specific failures.

---

## 3. Configuration

The mutation testing setup is configured inside `pyproject.toml` under `[tool.mutmut]`:

```toml
[tool.mutmut]
# The specific files targeted for mutation testing (logic-heavy, fast tests)
source_paths = [
    "src/utils/retry.py",
    "src/utils/pr_validator.py",
    "src/tools/text_extractor.py",
]
# Folders copied to the sandbox workspace so imports resolve correctly
also_copy = [
    "src/",
    ".github/",
]
# Targeted pytest selection to avoid running slow or unrelated tests
pytest_add_cli_args_test_selection = [
    "tests/test_retry.py",
    "tests/test_pr_validator.py",
    "tests/test_text_extractor.py",
]
# Disables plugins like cov/logfire to speed up test execution
pytest_add_cli_args = [
    "-p", "no:cov",
    "-p", "no:logfire",
]
```

---

## 4. Interpreting Results

* **Killed (🎉)**: A test failed because of the mutation. Your test suite successfully caught the bug.
* **Survived (🙁)**: All tests passed despite the mutation. This means either:
    1. **Test Gap**: A test assertion is missing for that logic branch.
    2. **Equivalent Mutation**: The change did not alter the program's output/semantic meaning (e.g. changing `<` to `<=` on a boundary where both behave identically due to other guards).
* **No Tests (🫥)**: No test executed the mutated line. Check that the tests targeting this file are properly configured and running.

---

## 5. Handling Survived Mutants

### Write Better Tests
Add new test cases to `tests/test_<name>.py` specifically covering the boundary conditions or logic that allowed the mutant to survive.

### Suppressing Trivial Mutants
If a mutation is trivial (e.g., mutating a debug log statement) or represents an equivalent mutation, you can tell `mutmut` to skip it by appending `# pragma: no mutate` to the line:

```python
logger.debug("Starting retry cycle")  # pragma: no mutate
```
