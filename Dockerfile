# Multi-stage Dockerfile for foss-launcher-skills tools.
#
# Build:   docker build -t foss-launcher-skills .
# Run:     docker run --rm foss-launcher-skills foss-gate
# Compose: docker compose up
#
# The image provides an isolated environment for running foss-launcher-skills
# entry points (foss-gate, foss-validate, foss-check, etc.) without requiring
# a local Python installation.

# ---------------------------------------------------------------------------
# Stage 1: dependency builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Copy dependency manifests first for layer caching
COPY pyproject.toml ./
COPY scripts/ ./scripts/

# Install base + dev dependencies into /install prefix
RUN pip install --no-cache-dir --prefix=/install ".[dev]"

# ---------------------------------------------------------------------------
# Stage 2: minimal runtime image
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY scripts/ ./scripts/
COPY skills/ ./skills/
COPY configs/ ./configs/
COPY pyproject.toml ./
COPY AGENTS.md ./
COPY CLAUDE.md ./

# Create writable directories for runtime artifacts
RUN mkdir -p knowledge output reports runs backlog

# Environment defaults (operators should override via -e or docker-compose)
ENV PYTHONPATH=/app/scripts \
    KNOWLEDGE_ROOT=/app/knowledge \
    CONTENT_REPO_PATH=/app/content

# Default entry point: local quality gate
ENTRYPOINT ["foss-gate"]
CMD ["--help"]

# Healthcheck: verify the package entry point is executable
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD foss-validate --help > /dev/null 2>&1 || exit 1
