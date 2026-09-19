# Base Python image
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd --create-home appuser
WORKDIR /app

# ── Stage: dependencies ──
FROM base AS deps
COPY pyproject.toml .
RUN pip install --no-cache-dir .[dev]

# Copy remaining source
COPY --chown=appuser . .
RUN pip install --no-cache-dir uvicorn[standard]>=0.29 litestar>=2.24 jinja2 pydantic-settings

# ── Stage: final ──
FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --chown=appuser . .

# Create data directory
RUN mkdir -p /app/data /app/cache

USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8080/health'); exit(0 if r.status_code == 200 else 1)"

# Run with uvicorn
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
