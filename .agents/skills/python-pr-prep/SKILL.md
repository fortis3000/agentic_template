---
name: python-pr-prep
description: Prepare current Python work for PR using latest best practices and gh cli
---

# Prepare current work for PR: Verify Tests Passing and Cleanup

**Objective:** Clean up temporary modifications, verify project constraints with `uv` and linting/testing suites (`ruff`, `bandit`, `pymarkdown`, `pytest`), ensure local validation checks pass, and prepare a GitHub pull request using the GitHub CLI (`gh`).

**Instructions:**

1. **Virtual Environment Setup & Dev Dependencies:**
   * Ensure dev dependencies are fully synchronized:
     ```bash
     uv sync --extra all
     ```
   * All subsequent commands, tests, and formatting checks should be prefixed and run with `uv run` to ensure consistency.

2. **Cleanup:**
   * Review currently modified files (`git status` or `git diff`). Remove any:
     * `print()` statements or lingering `breakpoint()` / `import pdb` traces. Use the standard logger from `src/utils/logger.py` where logging is needed.
     * Commented-out code blocks.
     * Temporary "hack" fixes or dangling `# TODO` comments that should be resolved in this PR.
   * **Documentation Check:** Verify that extensive (but non-redundant) documentation has been added or updated for any new functionality introduced in this PR (e.g., in `README.md` or dedicated markdown files).

3. **Verify with Bundled Validation Script:**
   * Run the pre-commit script to format code, check lints/security/markdown rules, and verify tests pass on changed files:
     ```bash
     make precommit
     ```
     or:
     ```bash
     bash precommit.sh
     ```
     *Note: If Docker is used (as recommended in python-coder), run these validation checks within the Docker sandbox as specified in the python-coder skill.*

4. **Report & Review:**
   * Summarize the cleanup and documentation status (e.g., "All tests passing, removed temporary prints, added user guide documentation for new feature").
   * **Action:** Ask the user to review the Git diff closely to ensure no intended code was accidentally removed.
   * **Commit:** Once reviewed, provide the command to commit the changes:
     ```bash
     git commit -m "Prepare for PR: format/lint code, verify tests pass, remove debug traces, and add documentation"
     ```
   * **Draft PR:** Provide the user with the exact `gh` CLI command to draft or create the PR.
     * *Example:* `gh pr create --title "Your PR Title" --body "Summary of changes..." --draft`

5. **Post-PR Cleanup (Git Worktrees):**
   * Once the pull request is merged or closed, clean up the worktree:
     * Navigate back to the repository root directory:
       ```bash
       cd ../..
       ```
     * Remove the worktree and delete the local branch:
       ```bash
       git worktree remove .worktrees/<branch-name>
       git branch -d <branch-name>
       ```

