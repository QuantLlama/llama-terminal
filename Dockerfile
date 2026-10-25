# Quantum Llama Terminal - cloud runtime image (web/API only).
# Desktop/Electron packaging is not part of this image.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app \
    APP_PORT=8050 \
    MT5_AUTO_LAUNCH=false

WORKDIR ${APP_HOME}

# System libraries: build toolchain for pinned wheels plus runtime
# libraries required by the scientific stack.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gnupg \
        gzip \
        wget \
        curl \
        libgomp1 \
        libfreetype6 \
        libpng16-16 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.deploy.txt ./requirements.deploy.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.deploy.txt

# Optional AI/model inference support (CPU build keeps the image small).
ARG WITH_TORCH=false
RUN if [ "$WITH_TORCH" = "true" ]; then \
        pip install --index-url https://download.pytorch.org/whl/cpu torch==2.2.2; \
    fi

COPY . .

# Writable runtime directories (mount volumes over these in production).
# The managed PostgreSQL runs major 16; a distro pg_dump (15) refuses to dump a
# newer server, so the client comes from the PGDG repository at the same major.
RUN install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p config outputs logs images \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser ${APP_HOME}

USER appuser

EXPOSE ${APP_PORT}

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${APP_PORT}/health" || exit 1

CMD ["sh", "-c", "uvicorn src.platform.api.main:app --host 0.0.0.0 --port ${APP_PORT} --proxy-headers --forwarded-allow-ips='*'"]
