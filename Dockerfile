# Production-grade image for the researchhub-engine.
# Multi-stage: deps staged, runtime kept minimal, runs as a non-root user,
# with a HEALTHCHECK and Playwright chromium (clerk scraper) installed.

FROM python:3.13-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libssl-dev \
        libffi-dev \
        unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Playwright browsers (needed for the clerk deed/plat scraper)
RUN python -m playwright install chromium --with-deps

# ---- runtime --------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

RUN groupadd --system app && useradd --system --gid app app \
    && apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libssl3 \
        curl \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=deps /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --from=deps /root/.cache/ms-playwright /ms-playwright

COPY backend ./backend
COPY alembic.ini .
COPY scripts ./scripts

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Data dir must be writable by the non-root user
RUN mkdir -p /app/data /app/evidence && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
