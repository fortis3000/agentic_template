---
name: python-coder
description: Software development workflow for Python agents/tools utilizing Git worktrees, Docker sandboxed execution, and SSDLC security practices.
---

# Python Coder Workflow Guide

**Objective:** Standardize the development process for Python agents, tools, and scripts using Git worktrees for workspace isolation, Docker containers for secure sandboxed execution, and SSDLC principles for high code quality and security.

## Core Workflow Steps

### 1. Worktree Isolation
Always isolate your development environments using Git worktrees. This prevents uncommitted files or diverging local configurations on the `master` branch from contaminating your work, and allows switching between different tasks instantly.

* **Create Worktree:** Run the following command from the repository root:
  ```bash
  git worktree add -b <branch-name> .worktrees/<branch-name> origin/master
  ```
* **Navigate to Worktree:**
  ```bash
  cd .worktrees/<branch-name>
  ```
  *Note: All subsequent commands, file modifications, and validation tests must be performed within this worktree directory to ensure isolation.*

---

### 2. Implementation & SSDLC Security Principles
When modifying or creating code, adhere strictly to the following secure software development principles:

* **Typing & Quality:** Enforce static typing and avoid any `Any` types where possible. Follow standard PEP 8 naming conventions.
* **No Secret Hardcoding:**
  * Never place credentials, API keys, or secrets directly in the source code.
  * Retrieve config values from environment variables or a configuration manager.
  * Never commit `.env` files or expose credentials in logs or shell traces.
* **Documentation Requirement:**
  * For every new feature, tool, or utility, write extensive documentation.
  * Update [README.md](file:///Users/user/Documents/projects/agentic_template/agentic_template/README.md) or create dedicated documentation files if needed.
  * Document API interfaces, usage examples, and installation/configuration prerequisites.
* **Extensive Testing:**
  * Prefer writing tests alongside or before implementation.
  * Place unit and integration tests under the `tests/` directory close to the code changed.

---

### 3. Docker-Sandboxed Validation
To isolate execution from the host system and ensure dependencies are correct, run all validation steps (formatting, linting, security scans, and tests) within a Docker container.

* **Build the Docker Image:**
  From the root of your worktree, build the image:
  ```bash
  docker build -f docker/Dockerfile -t agentic-template:latest .
  ```
* **Run Linting & Code Quality Checks:**
  ```bash
  # Format check
  docker run --rm -v "$(pwd)":/app agentic-template:latest uv run ruff format --check src/ tests/
  # Lint check
  docker run --rm -v "$(pwd)":/app agentic-template:latest uv run ruff check src/ tests/
  # Static type check
  docker run --rm -v "$(pwd)":/app agentic-template:latest uv run ty check src/ tests/
  ```
* **Run Bandit Security Analysis:**
  ```bash
  docker run --rm -v "$(pwd)":/app agentic-template:latest uv run bandit -c pyproject.toml -r src/
  ```
* **Run Unit Tests:**
  ```bash
  docker run --rm -v "$(pwd)":/app agentic-template:latest uv run pytest -v
  ```

---

### 4. Committing and PR Preparation
Once all checks pass inside the Docker sandbox:

1. Stage and commit your changes:
   ```bash
   git add -A
   git commit -m "feat(scope): implement new feature and write tests/docs"
   ```
2. Push to remote:
   ```bash
   git push -u origin HEAD
   ```
3. Submit a pull request on GitHub (e.g. using `gh pr create --fill --draft`).

---

### 5. Workspace Cleanup
After your PR is merged or closed, clean up the worktree to release disk space and maintain a tidy workspace.

1. Navigate back to the repository root directory:
   ```bash
   cd ../..
   ```
2. Prune the worktree and delete the local branch:
   ```bash
   git worktree remove .worktrees/<branch-name>
   git branch -d <branch-name>
   ```
