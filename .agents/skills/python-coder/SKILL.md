---
name: python-coder
description: Software development workflow for Python agents/tools utilizing Git worktrees, Docker sandboxed execution, and SSDLC security practices.
---

# Python Coder Workflow Guide

**Objective:** Standardize the development process for Python agents, tools, and scripts using Git worktrees for workspace isolation, Docker containers for secure sandboxed execution, and SSDLC principles for high code quality, typing compliance, and security checks.

---

## Step-by-Step Developer Lifecycle

### 1. Worktree Isolation

To isolate your development environment and avoid contaminating the `master` branch:

* **Automated Script (Recommended):**
  From the repository root, run the start script providing the issue number and optional branch name:

  ```bash
  bash .agents/skills/gh-cli/scripts/start_issue.sh <issue_number> [optional_branch_name]
  ```

* **Manual Command Fallback:**

  ```bash
  git worktree add -b <branch-name> .worktrees/<branch-name> origin/master
  ```

* **Navigate to Worktree:**

  ```bash
  cd .worktrees/<branch-name>
  ```

  *Note: Perform all subsequent edits, tests, and checks inside this worktree directory.*

---

### 2. Local Environment Synchronization

Always synchronize the Python environment to obtain correct dependencies:

```bash
uv sync --extra all
```

---

### 3. Implementation & Secure Coding Guidelines

Ensure compliance with SSDLC and code quality standards:

* **Static Typing**: Annotate variables and functions. Avoid using `Any`.
* **Zero Hardcoded Secrets**:
  * Never hardcode API keys, passwords, or tokens in source files.
  * Read configuration properties from environment variables or secure credential managers.
  * Never commit `.env` files or log raw token credentials.
* **Documentation**:
  * Keep documentation updated. Create or modify files under the `docs/` folder (such as `docs/README.md`, `docs/components.md`, `docs/diagrams.md`).
  * Use relative path links within codebase markdown documents so they remain portable.
* **Testing**:
  * Write test cases alongside code modifications.
  * Save tests under the `tests/` directory (e.g. using `pytest`).

---

### 4. Running Validation Checks

Before committing, run tests, linters, and security checks:

* **Docker-Sandboxed Validation (Recommended):**
  Ensures isolation from the host environment:

  ```bash
  # Build the container
  docker build -f docker/Dockerfile -t agentic-template:latest .

  # Run formatting, linting, type checks, security checks, and testing
  docker run --rm -v "$(pwd)":/app -v /app/.venv agentic-template:latest bash -c "
    set -e
    echo '=== Syncing lint and test dependencies ==='
    uv sync --locked --extra lint,test
    echo '=== Running pre-commit validations ==='
    uv run pre-commit run --all-files
  "
  ```

* **Local Fallback:**
  If Docker is not running or available:

  ```bash
  uv run pre-commit run --all-files
  ```

---

### 5. Git Commit & Semantic Message Standard

Stage your files and commit them using the Conventional Commit convention:

* **Format:** `<type>(<scope>)?(!)?: <description>`
* **Allowed Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
* **Command:**

  ```bash
  git add -A
  git commit -m "feat(sdk): implement new backend wrapper and add unit tests"
  ```

---

### 6. Pushing & Authenticating with GitHub

Before running any `gh` CLI commands, retrieve the GitHub PAT from your environment or credentials file:

```bash
# Locate and export the GitHub token
export GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' .env | cut -d= -f2- | xargs)

# If in a worktree and .env is in the project root:
export GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' ../../.env | cut -d= -f2- | xargs)

# Push the branch to origin
git push -u origin HEAD
```

---

### 7. Pull Request Submission & Template Validation

Every pull request must follow the structure in `.github/pull_request_template.md`.

* **Automated Submission (Recommended):**
  The script automatically runs Docker validations, commits your staged changes semantically, pushes them, and creates a draft PR:

  ```bash
  bash .agents/skills/gh-cli/scripts/submit_pr.sh <type> [scope] <description>
  ```

* **Manual PR Creation with Template:**
  1. Create a temporary file containing the PR template:
     ```bash
     cp .github/pull_request_template.md temp_pr_body.md
     # (Edit temp_pr_body.md to complete all sections and replace [Answer here] placeholders)
     ```
  2. Create the Pull Request using the body file:
     ```bash
     gh pr create --body-file temp_pr_body.md --draft
     ```
  3. Clean up the temporary file:
     ```bash
     rm temp_pr_body.md
     ```

* **PR Template Guidelines:**
  * Complete all required sections: **Summary**, **Key Changes**, **Discussion & Pitfalls**, and **Verification**.
  * Keep the guiding template questions in plain text inside the PR description; **do not delete them**.
  * Fully replace the `[Answer here]` placeholders with detailed verification, testing output, and rationale.

---

### 8. Cleanup

After the pull request has been merged or closed, prune the worktree to clean up the local environment:

1. Return to the project root:

   ```bash
   cd ../..
   ```

2. Remove the worktree and delete the local task branch:

   ```bash
   git worktree remove .worktrees/<branch-name>
   git branch -d <branch-name>
   ```
