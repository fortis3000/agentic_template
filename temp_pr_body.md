# Pull Request

## Summary
*What is the core goal of this change?*
Add support for configuring Arize Phoenix instance parameters via a dedicated `phoenix:` chapter in the YAML configuration file (`configs/agent_config.yaml`), resolving Issue #34.

*What is the current behavior vs the new behavior?*
Current behavior: Arize Phoenix instance parameters could only be controlled via environment variables (`PHOENIX_COLLECTOR_ENDPOINT`, `ENABLE_PHOENIX`) or hardcoded defaults.
New behavior: Parameters such as `enabled`, `project_name`, `collector_endpoint`, `host`, `port`, `auto_instrument`, and `api_key` can now be defined directly in the YAML configuration file under a dedicated `phoenix:` top-level chapter (or nested under `agent:`).

*Why is this change necessary now?*
To allow developers to customize and persist Arize Phoenix observability settings per configuration file without relying solely on environment variables.

## Key Changes
*What are the main files modified or added, and what is their role?*
- `src/agents/config.py`: Added `PhoenixConfigSchema` Pydantic model and updated `AgentConfigSchema` and `AgentYamlConfig` to include an optional `phoenix` field.
- `configs/agent_config.yaml`: Added example `phoenix:` configuration block with `enabled`, `project_name`, `collector_endpoint`, `host`, `port`, and `auto_instrument`.
- `src/evals/phoenix_service.py`: Updated service initialization to parse and apply `phoenix:` parameters from the YAML config with fallback to environment variables.
- `src/api/main.py`: Updated FastAPI lifespan handler to parse and apply `phoenix:` parameters from the YAML config file.
- `tests/test_phoenix_config.py`: Added unit tests for `PhoenixConfigSchema` validation and YAML config parsing.

*Are there any new dependencies, database schema changes, or configurations introduced?*
- Introduced the `phoenix:` top-level configuration chapter in YAML config files. No new external dependencies or database schema changes.

## Discussion & Pitfalls
*What architectural trade-offs or key assumptions were made?*
- Made the `phoenix:` section completely optional to ensure full backwards compatibility with existing YAML configuration files.

*Are there any security, privacy, performance, or scaling implications?*
- `api_key` and endpoint URLs can be configured, but environment variables still take precedence for `PHOENIX_COLLECTOR_ENDPOINT` if explicitly set.

*Did you consider any alternative approaches? If so, why were they rejected?*
- Considered adding `phoenix` parameters only under `agent:`, but top-level `phoenix:` chapter aligns with the requirement to have a separate chapter in the YAML config. Both top-level and nested `phoenix` blocks are supported.

## Verification
*What automated tests (unit, integration) did you run, and what were the results?*
- Ran `pytest tests/test_phoenix_config.py` (5 passed).
- Ran full test suite `pytest` (165 passed).
- Ran `pre-commit run --all-files` (all hooks passed: Ruff Format, Ruff Check, Ty Type Check, Bandit Security Check, Pymarkdown, SQLFluff, Pytest, Semgrep, Yamllint, Frontend Lint/Format).

*How can a reviewer manually test and verify these changes?*
- Parse `configs/agent_config.yaml` using `AgentYamlConfig.model_validate()` and verify `config.phoenix` attributes.
- Run `uv run python src/evals/phoenix_service.py` to confirm Phoenix service starts with settings loaded from `configs/agent_config.yaml`.

*Are there any logs, screenshots, or recordings demonstrating the fix/feature?*
- 165 unit tests passed cleanly in pytest suite.
