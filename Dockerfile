FROM python:3.10-slim@sha256:70f65c721aaddfb22b20ed6ec12606c59d9592493c5fcb6639f3d0e8ba3fbc10 AS builder

ARG UV_VERSION=0.11.18

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY packages/inferra-core ./packages/inferra-core
COPY src ./src
COPY docs/inferra_prompt.md ./inferra_prompt.md

RUN pip install --no-cache-dir "uv==${UV_VERSION}" \
    && pip install --no-cache-dir --no-deps ./packages/inferra-core \
    && python -m uv export --frozen \
        --extra async \
        --extra semantic \
        --extra reasoning \
        --extra observability \
        --format requirements.txt \
        --no-emit-project \
        --no-emit-package inferra-core \
        --output-file /tmp/requirements.lock \
    && pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock \
    && find /usr/local -type d -name __pycache__ -prune -exec rm -rf {} +

FROM python:3.10-slim@sha256:70f65c721aaddfb22b20ed6ec12606c59d9592493c5fcb6639f3d0e8ba3fbc10

RUN apt-get update \
    && apt-get install -y --no-install-recommends pandoc \
    && command -v pandoc \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system inferra \
    && useradd --system --gid inferra --home-dir /app --shell /usr/sbin/nologin inferra

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder --chown=inferra:inferra /app/src ./src
COPY --from=builder --chown=inferra:inferra /app/pyproject.toml ./
COPY --from=builder --chown=inferra:inferra /app/uv.lock ./
COPY --from=builder --chown=inferra:inferra /app/inferra_prompt.md ./inferra_prompt.md

USER inferra

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/live', timeout=5)" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "8", "--backlog", "8192", "--no-access-log"]
