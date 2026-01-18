# Multi-stage build for optimized image size
FROM python:3.11-slim AS builder

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.7.1 \
    POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    $POETRY_HOME/bin/poetry --version

# Set working directory
WORKDIR /app

# Copy dependency files first (for better layer caching)
COPY pyproject.toml ./
COPY poetry.lock* ./

# Configure Poetry to create venv in project
RUN $POETRY_HOME/bin/poetry config virtualenvs.in-project true && \
    $POETRY_HOME/bin/poetry config virtualenvs.create true

# Copy source code (needed to install the package)
COPY src/ ./src/

# Install dependencies AND the package itself (no --no-root flag)
RUN $POETRY_HOME/bin/poetry install --only=main && \
    rm -rf $POETRY_CACHE_DIR

# Verify venv was created (helps debug if there's an issue)
RUN test -d /app/.venv || (echo "ERROR: .venv not found after poetry install" && ls -la /app && exit 1)

# Production stage
FROM python:3.11-slim

# Install runtime dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# Copy virtual environment from builder (includes installed package)
COPY --from=builder /app/.venv /app/.venv

# Set working directory
WORKDIR /app

# Copy application code (package already installed in venv from builder stage)
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser pyproject.toml /app/

# Make scripts executable
RUN chmod +x /app/.venv/bin/*

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP="cold_emailer.web.app:app" \
    FLASK_ENV="production"

# Create data directories with proper permissions
RUN mkdir -p /app/data /app/logs /app/config && \
    chown -R appuser:appuser /app/data /app/logs /app/config

# Switch to non-root user
USER appuser

# Expose web interface port
EXPOSE 5000

# Default command: run web interface
# Override with docker run or docker-compose to use CLI commands
# Example: docker run ... cold-emailer cold-emailer init-db
CMD ["python", "-m", "cold_emailer.web.app"]
