---
name: python-coder
description: Software development workflow for Python agents/tools utilizing Git worktrees, Docker sandboxed execution, and SSDLC security practices.
---

# Python Developer Lifecycle Guide

**Objective:** Standardize the development process for Python agents, tools, and scripts using Git worktrees for workspace isolation, Docker containers for secure sandboxed execution, and SSDLC principles for high code quality, typing compliance, security checks, and PR preparation.

This workflow is structured into four distinct phases:
1. **Phase 1**: Setup & Environment Isolation
2. **Phase 2**: Code Implementation (Delegated to `/implement`)
3. **Phase 3**: Validation & PR Preparation
4. **Phase 4**: Submission & Cleanup

---

## Phase 1: Setup & Environment Isolation

Before editing any code, always isolate your working directory to avoid contaminating the main branch:

### 1. Worktree Isolation
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

### 2. Environment Synchronization
Always synchronize the Python environment to obtain correct dependencies:
```bash
uv sync --extra all
```

---

## Phase 2: Code Implementation (Delegated to `/implement`)

All actual coding, bug fixing, or feature implementations should be executed using the `/implement` skill:
* **Invoke Implement**: Use the `implement` skill to execute code changes.
* **Test-Driven Development**: Where possible, use `/tdd` at pre-agreed seams.
* **Codebase Glossary**: Respect the domain-modeling glossary, naming conventions, and ADRs.
* **Type Annotations**: Always use static typing. Avoid introducing `Any`.

---

## Phase 3: Validation & PR Preparation

Once the implementation is complete, perform a thorough cleanup and run validation suites before committing or proposing a PR:

### 1. Code Cleanup Checklist
Review modified files (`git status` or `git diff`) and ensure you:
* **Remove Debug Artifacts**: Remove all `print()` statements, `breakpoint()`, or `import pdb` traces. Use the project's standard logger (`src/utils/logger.py`) if logging is needed.
* **Remove Commented-out Code**: Ensure there are no leftover commented-out code blocks.
* **Address Temporary Fixes**: Resolve temporary hacks and lingering `# TODO` comments that should be resolved in this PR.
* **Verify Documentation**: Update relevant documentation under the `docs/` folder or in `README.md` to reflect changes. Use relative paths for markdown links.

### 2. Pre-Commit Validation Checks
Run tests, linters, and security checks:
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

## Phase 4: Submission & Cleanup

After verifying that all checks pass successfully:

### 1. Semantic Commits
Stage files and commit them using the Conventional Commit convention:
* **Format:** `<type>(<scope>)?(!)?: <description>`
* **Allowed Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
* **Command:**
  ```bash
  git add -A
  git commit -m "feat(sdk): implement new backend wrapper and add unit tests"
  ```

### 2. Pushing & GitHub Authentication
Always export the GitHub PAT from `.env` first before running `gh` commands, as `gh` prefers environment tokens over keychain credentials:
```bash
# Locate and export the GitHub token (adjust path if running in a worktree)
export GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' ../../.env | cut -d= -f2- | xargs)

# Push the branch to origin
git push -u origin HEAD
```
*Note: Avoid the default `gh issue view` or `gh pr view` TUI commands, as they can cause token permission errors. Request explicit fields instead:*
```bash
gh issue view <n> --json number,title,body,state,labels
gh pr view <n>   --json number,title,body,state,headRefOid,url
```

### 3. Creating the Pull Request
Every pull request must follow the structure in `.github/pull_request_template.md`:
* **Automated Submission (Recommended):**
  This script runs validations, commits semantically, pushes, and creates a draft PR:
  ```bash
  bash .agents/skills/gh-cli/scripts/submit_pr.sh <type> [scope] <description>
  ```
* **Manual PR Creation with Template:**
  1. Copy and fill the template:
     ```bash
     cp .github/pull_request_template.md temp_pr_body.md
     # (Edit temp_pr_body.md, replacing all [Answer here] placeholders)
     ```
  2. Create draft PR:
     ```bash
     gh pr create --body-file temp_pr_body.md --draft
     ```
  3. Clean up the temporary file:
     ```bash
     rm temp_pr_body.md
     ```
  *Note: Make sure to keep the template's guiding questions in plain text inside the final PR description.*

### 4. Worktree Cleanup
After the pull request is merged or closed, clean up the local branch and worktree:
1. Return to the project root:
   ```bash
   cd ../..
   ```
2. Remove the worktree and delete the local task branch:
   ```bash
   git worktree remove .worktrees/<branch-name>
   git branch -d <branch-name>
   ```
