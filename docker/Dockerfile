FROM python:3.12-slim

ARG APP_UID=1654

ENV LISTEN_PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY data ./data
COPY run.py ./run.py

RUN test -f /app/app/static/css/app.css \
    && groupadd --gid "$APP_UID" app \
    && useradd --uid "$APP_UID" --gid "$APP_UID" --no-create-home --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /instance/link_previews /instance/thumbnails /instance/uploads \
    && chown -R "$APP_UID:$APP_UID" /app /instance /ms-playwright

EXPOSE 8080
VOLUME ["/instance"]

USER $APP_UID

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; [urllib.request.urlopen(f'http://127.0.0.1:8080{path}', timeout=4).close() for path in ('/', '/assets/css/app.css')]"]

CMD ["gunicorn", "--bind=0.0.0.0:8080", "--workers=1", "--threads=4", "--timeout=90", "run:app"]
