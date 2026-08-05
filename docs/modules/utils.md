# Shared Utilities Subsystem (`src/utils/`)

This document provides documentation for shared utility packages supporting logging, fault tolerance, PR validation, and external service connectors.

---

## 1. Overview & Components

Key files:
- [`src/utils/logger.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/utils/logger.py): Structured logger factory (`get_logger`).
- [`src/utils/retry.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/utils/retry.py): Exponential backoff retry utilities (`retry_async`, `retry_sync`).
- [`src/utils/pr_validator.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/utils/pr_validator.py): Pull request description and commit message validator.
- [`src/utils/google_sheets.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/utils/google_sheets.py): Google Sheets API wrapper.

---

## 2. Structured Logger (`src/utils/logger.py`)

Provides standardized logger instances:

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Service initialized", extra={"module": "api"})
```

---

## 3. Retry Mechanism (`src/utils/retry.py`)

Handles transient network errors, rate limits (HTTP 429), and connection resets across tool and model executions:

- `retry_async(coro_fn, retries=3, initial_delay=1.0, backoff_factor=2.0)`: Wraps asynchronous callables with jittered exponential backoff.
- `retry_sync(fn, retries=3, initial_delay=1.0, backoff_factor=2.0)`: Wraps synchronous callables.

---

## 4. PR & Commit Validator (`src/utils/pr_validator.py`)

Enforces repository standards before pull requests are merged:
1. **Semantic Commit Validation**: Validates Conventional Commit format (`feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`).
2. **PR Template Verification**: Verifies that PR descriptions contain all sections specified in `.github/pull_request_template.md` without leftover default placeholders.
