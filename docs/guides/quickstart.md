# Developer Quickstart & Environment Setup Guide

This guide walks you through setting up your local development environment for the Standardized Agentic Project Template.

---

## 1. Prerequisites

Ensure you have the following installed on your system:
- **Python**: Version **3.13** (required).
- **`uv` Package Manager**: Fast Python package installer and dependency resolver.
- **Node.js & npm**: Version **18+** (required for Svelte 5 + Vite web frontend).
- **Git**: For version control.
- **Docker & Docker Compose** (Optional, for running Qdrant and Arize Phoenix in containers).

---

## 2. Installing Dependencies

1. **Install `uv`** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone Repository & Sync Environment**:
   ```bash
   cd agentic_template
   
   # Install Python dependencies
   uv sync --extra all

   # Install Frontend (Svelte 5 UI) Node dependencies
   npm install --prefix frontend
   ```

   Alternatively, run the Makefile target to install both Python and Node dependencies in one step:
   ```bash
   make install_dev_dependencies
   ```

3. **Install Pre-Commit Git Hooks**:
   ```bash
   uv run pre-commit install
   ```

---

## 3. Environment Variables & Secret Management (`.env`)

Copy `.env.example` to `.env` to configure your local secret keys:

```bash
cp .env.example .env
```

The `.env` file is strictly reserved for sensitive API keys and personal access tokens:

```ini
# LLM Provider API Keys
GEMINI_API_KEY="your-gemini-api-key"
OPENAI_API_KEY="your-openai-api-key"
ANTHROPIC_API_KEY="your-anthropic-api-key"

# GitHub Personal Access Token (for gh CLI and PR tools)
GITHUB_TOKEN="your-github-pat-token"
```

> [!NOTE]
> System settings, Arize Phoenix telemetry endpoints (`phoenix:`), Qdrant vector database collections (`tools:`), and model parameters are defined centrally in **`configs/agent_config.yaml`**, rather than `.env`.
>
> Never commit `.env` or sensitive secret keys to source control. `.env` is listed in `.gitignore`.

---

## 4. Shell Environment Loader Script

To export `GITHUB_TOKEN` and project secrets into your active shell session for `gh` CLI commands:

```bash
source .agents/scripts/load_env.sh
```

If you use [direnv](https://direnv.net), the `.envrc` file automatically runs this loader whenever you `cd` into the project workspace or Git worktrees.

---

## 5. Verifying Installation

Run the test suite and pre-commit validations to confirm local environment readiness:

```bash
# Run pytest suite
uv run pytest

# Run pre-commit quality checks
make precommit
```

If all checks pass, your local environment is fully configured and ready for development!
