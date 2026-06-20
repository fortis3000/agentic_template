# Build context: project root (run with `docker build -f docker/Dockerfile .`)
FROM python:3.13-slim

WORKDIR /app

# Install uv from the official image (faster and avoids pip warnings)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Install dependencies first (cached unless pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# Copy source code
COPY src/ ./src/

# Activate the virtual environment by default
ENV PATH="/app/.venv/bin:$PATH"

CMD ["bash"]
