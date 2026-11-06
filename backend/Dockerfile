# syntax=docker/dockerfile:1.7
# The API and the background worker (same image, different command). Build from the repository root:
#   docker build -f backend/Dockerfile -t clearhire-api .

FROM python:3.12-slim-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*
ENV PATH=/venv/bin:$PATH PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HOME=/models
RUN python -m venv /venv
# CPU PyTorch: the embedding model is small; the GPU is left to the LLM
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0
WORKDIR /src
COPY backend/pyproject.toml backend/README.md backend/
COPY backend/src backend/src
RUN pip install ./backend
# the C++ skill matcher (pybind11); Clearhire falls back to Python without it, this image never does
COPY native native
RUN pip install ./native && python -c "import clearhire_native"
# bake the embedding model in, so the container never downloads anything at runtime
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('intfloat/multilingual-e5-small')"

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home --home-dir /app clearhire \
    && mkdir -p /data/files && chown clearhire /data/files
COPY --from=build /venv /venv
COPY --from=build /models /models
WORKDIR /app
COPY backend/alembic.ini ./
COPY backend/src ./src
COPY datasets ./datasets
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    CLEARHIRE_STORAGE_DIR=/data/files
USER clearhire
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
# behind Caddy on a private network: trust its X-Forwarded-For, so rate limits see the real client
CMD ["uvicorn", "clearhire.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
