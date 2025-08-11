FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy project metadata and install dependencies first (better layer caching)
COPY pyproject.toml uv.lock README.md ./

# Copy source earlier so the local project can be installed by uv
COPY src ./src

# Install build tools and project dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev


# Ensure app directories exist (logs are persisted via bind/volume in compose)
RUN mkdir -p /app/logs /data

# Use uv to run the console script defined in pyproject
CMD ["uv", "run", "tg-bot"]


