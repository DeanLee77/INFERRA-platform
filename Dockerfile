FROM python:3.10-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY src ./src
COPY docs/inferra_prompt.md ./inferra_prompt.md

RUN pip install --no-cache-dir ".[async,semantic,reasoning,observability]" \
    && find /usr/local -type d -name __pycache__ -prune -exec rm -rf {} +

FROM python:3.10-slim

RUN groupadd --system inferra \
    && useradd --system --gid inferra --home-dir /app --shell /usr/sbin/nologin inferra

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder --chown=inferra:inferra /app/src ./src
COPY --from=builder --chown=inferra:inferra /app/pyproject.toml ./
COPY --from=builder --chown=inferra:inferra /app/inferra_prompt.md ./inferra_prompt.md

USER inferra

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/live', timeout=5)" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "8", "--backlog", "8192", "--no-access-log"]
