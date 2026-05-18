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
    libcairo2 \
    libffi8 \
    kbd \
    procps \
    libportaudio2 \
    libasound2-plugins \
    alsa-utils \
    ffmpeg \
    libsndfile1 \
    libegl1 \
    libegl-mesa0 \
    libgl1 \
    libglx0 \
    libopengl0 \
    libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 audioshuttle && useradd -r -m -u 1000 -g audioshuttle audioshuttle

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src ./src

# Install multimodal deps
RUN pip install --no-cache-dir librosa pillow scipy matplotlib sounddevice

# USER audioshuttle

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/')" || exit 1

CMD ["audioshuttle", "--transport=standalone", "--host=0.0.0.0", "--port=8765", "--no-browser", "--no-tray"]

EXPOSE 8765