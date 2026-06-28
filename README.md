# Standartized Agentic Project Template

## Project Organization

    ├── Makefile           <- Makefile with commands like `make precommit`
    ├── README.md          <- The top-level README for developers using this project.
    ├── pyproject.toml     <- Project configuration for dependencies, linting, formatting, etc.
    ├── uv.lock            <- The lock file for reproducing the analysis environment.
    ├── .env.example       <- Template for environment variables and API keys
    ├── data
    │   ├── external       <- Data from third party sources.
    │   ├── interim        <- Intermediate data that has been transformed.
    │   ├── processed      <- The final, canonical data sets for modeling.
    │   └── raw            <- The original, immutable data dump.
    │
    ├── notebooks          <- Jupyter notebooks.
    │
    ├── references         <- Data dictionaries, manuals, and all other explanatory materials.
    │
    ├── docker             <- Docker configurations for agent-app and Arize Phoenix setup.
    │
    └── src                <- Source code for use in this project.
        ├── __init__.py    <- Makes src a Python module
        │
        ├── agents         <- SDK-agnostic agent implementations and orchestration.
        │
        ├── evals          <- Evaluation frameworks (Arize Phoenix, custom LLM evals).
        │
        ├── prompts        <- System and template prompts.
        │
        ├── tools          <- Custom tools and functional integrations.
        │
        └── utils          <- Shared utilities (e.g., logging)


## Logging

This project provides a general-purpose logger utility in `src/utils/logger.py`.

**Usage Example:**

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("This is an info message.")
logger.error("This is an error message.")
```

You can attach this logger to any module or script in the project.

## Agentic Framework

The template provides an SDK-agnostic agent interface and generator that spawns Google Antigravity SDK agents from YAML configurations.

### Directory Structure for Agents
- **`src/agents/`**: Core definitions, abstractions, prompt management, and SDK wrappers.
- **`src/prompts/`**: Directory for reusable system and user prompt templates.
- **`configs/`**: Directory for agent YAML configuration files.

### Spawning and Calling Agents (Usage Example)

Here is a working example demonstrating how to load a configuration, render templates, and execute an agent in both streaming and non-streaming modes:

```python
import asyncio
from src.agents import AntigravityAgentGenerator, TextPart, ImagePart

async def main():
    # 1. Initialize the agent generator
    generator = AntigravityAgentGenerator(prompt_base_dir="src/prompts")

    # 2. Create the agent from YAML config, supplying system prompt variables dynamically
    agent = generator.create_agent(
        "configs/agent_config.yaml",
        system_variables={"role": "Senior AI Architect"}
    )

    # 3. Call the agent (non-streaming)
    # Supplying a dictionary will format the default user prompt from the config
    response = await agent.call(inputs={"query": "Explain quantum computing in one sentence."})
    print("--- Non-streaming Response ---")
    print(response)

    # 4. Call the agent (streaming)
    print("\n--- Streaming Response ---")
    async for chunk in agent.call_stream(inputs="Tell me a joke about Python."):
        print(chunk, end="", flush=True)
    print()

    # 5. Multimodal Call (Text and Image)
    # image = ImagePart.from_file("data/raw/example.png")
    # response = await agent.call(inputs=["Describe this image", image])

if __name__ == "__main__":
    asyncio.run(main())
```

## Observability with Arize Phoenix

This project provides integrated OpenTelemetry and OpenInference instrumentation to trace agent calls and tool execution automatically.

### Running with Docker Compose (Recommended)
You can spawn the Arize Phoenix service and run the agent application in Docker:

1. **Start the services**:
   ```bash
   make docker-up
   ```
   This builds the agent image and launches both the `phoenix` and `agent-app` containers.

2. **Access the Phoenix UI**:
   Open your browser and navigate to: [http://localhost:6060](http://localhost:6060)

3. **OTLP Endpoints**:
   - gRPC endpoint: `http://localhost:4317`
   - HTTP/protobuf endpoint: `http://localhost:6006/v1/traces`

Any agent execution inside the `agent-app` container (or run locally on the host pointing to the collector endpoint) will emit traces that appear in the Phoenix dashboard.

### Programmatic Setup (Local Python)
If you prefer not to use Docker, you can launch the service and run a demo agent session programmatically:

```bash
uv run python src/evals/phoenix_service.py
```
This script will:
- Spawn a local Arize Phoenix UI and collector server.
- Automatically configure the global OpenTelemetry tracer.
- Execute a demo session (running an agent and a custom weather tool) to generate sample traces.
- Keep the server running so you can inspect how the agent works directly in the UI.

--------

## Goals
- Reduce time to establish a repo specifically for Agentic AI needs.
- To align data scientists in terms of skills and tools used.
- Make project standard, easier to observe and predictable.

## Description

### Project structure

The current architecture is based on [Cookiecutter DS](https://github.com/drivendata/cookiecutter-data-science) approach. The reasoning behind it you can find [here](http://drivendata.github.io/cookiecutter-data-science/).

### Code versioning tools
To track, keep and share your codings [git](https://git-scm.com/) and [GitHub](https://github.com/) services are required.

### Default programming language
To leverage modern programming stack it is recommended to start with [Python 3.13](https://www.python.org/downloads/release/python-3130/) as default.

### Dependency management
To follow Single-Source-Of-Truth concept it makes sense to use [pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) to store project configuration. `pyproject.toml` configuration file allows to use the same configuration on different project steps: CI/CD, dev, test, prod etc.

#### uv
Newly announced [uv tool](https://github.com/astral-sh/uv).

To initialize the virtual environment and install all dependencies:
```bash
uv sync --extra all
```

To run any script or command inside the environment:
```bash
uv run python <script.py>
```

To update `uv.lock` file:
```bash
uv lock --upgrade
```

### Codestyle: ruff
Both for code linting and formatting Ruff package is proposed to use. See [here](https://docs.astral.sh/ruff/) for more details.

Commands:
```bash
uv run ruff format .
uv run ruff check .

uv run ruff check . --fix
```

### Security: Semgrep
A custom Semgrep configuration is provided under `.semgrep/rules.yaml` to scan the codebase for security concerns, such as hardcoded API key prefixes in Python files.

### CI/CD: GitHub Actions

As a baseline, CI with integrated code style is provided (see `.github/workflows/ci.yml`). The current setup is based on using public Actions and configuring CI with `pyproject.toml` file. It is also possible to use custom Actions.

### Test suite: pytest

This project uses [pytest](https://docs.pytest.org/en/stable/) for running tests and [pytest-cov](https://pytest-cov.readthedocs.io/en/latest/) for measuring test coverage.

To run the tests and generate a coverage report, use the following commands:

```bash
uv run coverage run -m pytest -v .
uv run coverage report -m
```

The CI is configured to fail if the test coverage is below 80%.


## Getting started
1. Create repo from the template

While creating repo, choose the current one as a template. Check [tutorial](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository) for more details.

It is also possible to use this repository as a template in GitHub interface.

2. Install, compile and activate virtual environment
See [uv](#uv)

3. Change parameters `pyproject.toml` if needed.
4. Tweak CI configuration `.github/workflows/ci.yml` if needed.
5. Put you source code in `src` folder.
6. Enjoy coding :)

## Best practices

### Makefile
Codestyle functionality could be applied locally using the Makefile created and the following command:

```bash
make precommit
```

### Secure Coding Standards

Secure coding standards are defined in [.agents/CONTEXT.md](file://./.agents/CONTEXT.md) and focus on:
1. **Tool Input Validation** (using strict Pydantic schemas).
2. **No Shell Execution** (restricting `run_command` usage).
3. **Pre-Commit Remediation Loop** (automatic / standard linting and Semgrep compliance).

### Pre-commit Hooks

Git pre-commit hooks are configured in [.pre-commit-config.yaml](file://./.pre-commit-config.yaml) to run on commit:
- `end-of-file-fixer` (ensures files end with a single newline)
- `trailing-whitespace` (trims trailing whitespaces)
- `Ruff Format` (formats Python code)
- `Ruff Check` (lints Python code)
- `Ty Type Check` (verifies type safety)
- `Bandit Security Check` (checks for common security issues)
- `Pymarkdown Scan` (verifies Markdown compliance)
- `Pytest Suite` (runs the entire test suite on every commit to ensure no regressions)
- `Semgrep Scan` (runs Semgrep security scans on changed Python files using the custom rules in `.semgrep/rules.yaml` with the `--error` flag to block commits with findings)

To activate these hooks locally, run:
```bash
uv run pre-commit install
```

To run all hooks manually across all files:
```bash
uv run pre-commit run --all-files
```

## Isolated Development Workflow

To ensure secure software development lifecycle (SSDLC) principles, workspace isolation, and reproducible test results, this repository supports and enforces the use of Git worktrees and Docker sandboxing.

### 1. Worktree Isolation
Create a dedicated Git worktree inside `.worktrees/` to work on an issue. This keeps your main workspace clean and allows for parallel development:
```bash
bash .agents/skills/gh-cli/scripts/start_issue.sh <issue_number> [optional_branch_name]
cd .worktrees/<branch_name>
```

### 2. Docker Sandboxed Validation
To execute tests and linters without contaminating the host system and ensure correct dependencies, build and run inside a Docker container:
```bash
# Build the validation container
docker build -f docker/Dockerfile -t agentic-template:latest .

# Run validations (format, lint, security scans, and tests)
docker run --rm -v "$(pwd)":/app agentic-template:latest bash -c "
  uv run ruff format --check src/ tests/ && \
  uv run ruff check src/ tests/ && \
  uv run ty check src/ tests/ && \
  uv run bandit -c pyproject.toml -r src/ && \
  uv run pytest -v
"
```

### 3. Submit Pull Request
When inside the worktree, run the submission script to validate, commit semantically, push, and open a draft PR:
```bash
bash .agents/skills/gh-cli/scripts/submit_pr.sh <type> [scope] <description>
```

### 4. Cleanup
After merging or completing the work, return to the project root and clean up the worktree:
```bash
cd ../..
git worktree remove .worktrees/<branch-name>
git branch -d <branch-name>
```
