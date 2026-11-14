# syntax=docker/dockerfile:1

# ---- Build stage: install dependencies into a virtualenv ----
FROM python:3.14-slim AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

# ---- Runtime stage: slim image, non-root user ----
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

RUN useradd --create-home --uid 10001 app
COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health/live', timeout=2)"

# Only trust X-Forwarded-* headers from these IPs. Set FORWARDED_ALLOW_IPS to the
# hosting platform's proxy range in staging/production (uvicorn reads it natively).
ENV FORWARDED_ALLOW_IPS=127.0.0.1

# One process per container; scale by running more containers.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
