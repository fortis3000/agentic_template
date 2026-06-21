---
name: python-pr-prep
description: Prepare current Python work for PR using latest best practices and gh cli
---

# Prepare current work for PR: Verify Tests Passing and Cleanup

**Objective:** Clean up temporary modifications, verify project constraints with `uv` and linting/testing suites (`ruff`, `bandit`, `pymarkdown`, `pytest`), ensure local validation checks pass, and prepare a GitHub pull request using the GitHub CLI (`gh`).

**Instructions:**

1. **Virtual Environment Setup & Dev Dependencies:**
   * Ensure you are executing commands within the local virtual environment `.venv`.
   * Activate the environment:
     ```bash
     source .venv/bin/activate
     ```
   * Ensure dev dependencies are fully synchronized:
     ```bash
     uv sync --extra all
     ```

2. **Cleanup:**
   * Review currently modified files (`git status` or `git diff`). Remove any:
     * `print()` statements or lingering `breakpoint()` / `import pdb` traces. Use the standard logger from `src/utils/logger.py` where logging is needed.
     * Commented-out code blocks.
     * Temporary "hack" fixes or dangling `# TODO` comments that should be resolved in this PR.

3. **Verify with Bundled Validation Script:**
   * Run the bundled pre-commit script to format code, check lints/security/markdown rules, and verify tests pass on changed files:
     ```bash
     bash .agents/skills/python-pr-prep/scripts/precommit.sh
     ```

4. **Report & Review:**
   * Summarize the cleanup status (e.g., "All tests and precommit checks passing, removed temporary prints, fixed type warnings").
   * **Action:** Ask the user to review the Git diff closely to ensure no intended code was accidentally removed.
   * **Commit:** Once reviewed, provide the command to commit the changes:
     ```bash
     git commit -m "Prepare for PR: format/lint code, verify tests pass, and remove debug traces"
     ```
   * **Draft PR:** Provide the user with the exact `gh` CLI command to draft or create the PR.
     * *Example:* `gh pr create --title "Your PR Title" --body "Summary of changes..." --draft`
