# Standardized Agentic Project Template - Documentation

Welcome to the documentation for the Standardized Agentic Project Template. This documentation directory provides a structured explanation of the codebase components, their design, integrations, and developer workflows.

## Documentation Structure

The documentation is organized into the following sections:

- **[README.md](README.md)** (this file): Introduction and documentation roadmap.
- **[components.md](components.md)**: Detailed breakdown of the repository's modules, including agent SDK abstractions, backend wrappers, observability frameworks, and validation gates.
- **[diagrams.md](diagrams.md)**: Graphical representations of the system, including:
  - **High-Level System Architecture**: Shows relationships and boundaries between the five core layers.
  - **Runtime Execution Flow**: Traces an agent invocation, tool resolution, and telemetry spans from query to response.
  - **Developer Contribution Loop**: Visualizes the secure SDLC pipeline, including worktrees, pre-commit validation, and automated pull request template checks.

## Repository Overview

This project template is designed to:

1. **Accelerate Agent Development**: Establish a clean, standardized workspace utilizing state-of-the-art Python dependencies managed by `uv`.
2. **Ensure Framework Agnosticism**: Standardize interface patterns so that agents can be built using the Google Antigravity SDK, Pydantic AI, or any other agent framework under a unified API.
3. **Pave the Road for Secure Coding**: Enforce automatic type checking, security static scans, and validation checks using pre-configured pre-commit git hooks.
4. **Provide Complete Observability**: Automatically trace agent calls and tool usage out-of-the-box using OpenTelemetry instrumentations routed to Arize Phoenix.

## Developer Contribution Workflow

To contribute to this repository, follow these sequential steps:

1. **Create Worktree**: Spawn an isolated git worktree using the script: `bash .agents/skills/gh-cli/scripts/start_issue.sh <issue_number>`
2. **Implement the Task**: Write the required features or fixes under the `src/` directory.
3. **Write Tests**: Implement matching test coverage in the `tests/` directory.
4. **Run Tests**: Execute `make precommit` locally to run pytest and formatting/linting validations.
5. **Update Docs**: Modify or add documentation files under the `docs/` folder.
6. **Commit**: Stage files and commit them using the Conventional Commit format (e.g. `feat(sdk): add new wrapper`).
7. **Push**: Push your task branch to origin.
8. **Create a PR & Fill Template**: Submit a pull request and fill the PR template using the `gh` command (e.g. `gh pr create --body-file .github/pull_request_template.md` and filling out the template sections), or via the automated submission script: `bash .agents/skills/gh-cli/scripts/submit_pr.sh <type> [scope] <description>`
