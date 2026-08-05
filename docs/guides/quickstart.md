# Developer Quickstart & Environment Setup Guide

This guide walks you through setting up your local development environment for the Standardized Agentic Project Template.

---

## 1. Prerequisites

Ensure you have the following installed on your system:
- **Python**: Version **3.13** (required).
- **`uv` Package Manager**: Fast Python package installer and dependency resolver.
- **Git**: For version control.
- **Docker & Docker Compose** (Optional, for running Qdrant and Arize Phoenix in containers).

---

## 2. Installing `uv` & Dependencies

1. **Install `uv`** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. **Clone Repository & Sync Environment**:
   ```bash
   cd agentic_template
   uv sync --extra all
   ```
   This command creates a local `.venv` environment and installs all production, dev, and test dependencies.

---

## 3. Environment Variables Configuration

Copy `.env.example` to `.env` and fill in your API credentials:

```bash
cp .env.example .env
```

Key environment variables:
```ini
# LLM Provider API Keys
GEMINI_API_KEY=your_gemini_api_key
OPENAI_API_KEY=your_openai_api_key

# Arize Phoenix Telemetry
ENABLE_PHOENIX=true
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
PHOENIX_PROJECT_NAME=agentic-template

# Vector Database (Qdrant)
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=agentic_docs
```

> [!CAUTION]
> Never commit `.env` or sensitive secret keys to source control. `.env` is listed in `.gitignore`.

---

## 4. Verifying Installation

Run `pytest` to confirm the local environment is configured correctly:

```bash
uv run pytest
```
If all tests pass, your local environment is ready for development!
