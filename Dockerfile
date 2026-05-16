# syntax=docker/dockerfile:1
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libffi-dev \
    libcairo2-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir ."[web,stt]"

FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2-dev \
    libffi8 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 audioshuttle && useradd -r -u 1000 -g audioshuttle audioshuttle

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src ./src
COPY pyproject.toml .

RUN pip install --no-cache-dir ."[web,stt]"

USER audioshuttle

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

CMD ["audioshuttle", "--transport=stdio", "--no-browser"]

EXPOSE 8765