# Stage 1: Builder
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Hardened Runtime
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    CACHE_FILE_PATH=/data/mpt_cache.json

# Create non-root SRE service user (UID 10001)
RUN groupadd -g 10001 sre && \
    useradd -u 10001 -g sre -s /sbin/nologin -M sre && \
    mkdir -p /data /app && \
    chown -R sre:sre /data /app

COPY --from=builder /install /usr/local
COPY --chown=sre:sre src/ /app/src/

WORKDIR /app
USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]