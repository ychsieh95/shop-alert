FROM tiangolo/uwsgi-nginx-flask:python3.12

ENV LISTEN_PORT=8080 \
    STATIC_PATH=/app/app/static \
    STATIC_URL=/assets \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt \
    && python3 -m playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

COPY uwsgi.ini /app/uwsgi.ini
COPY run.py /app/run.py
COPY app /app/app
COPY data /app/data

RUN test -f /app/app/static/css/app.css \
    && ln -s /app/app/static /app/static \
    && mkdir -p /instance/uploads /instance/link_previews \
    && ln -s /instance /app/instance

EXPOSE 8080
VOLUME ["/instance"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; [urllib.request.urlopen(f'http://127.0.0.1:8080{path}', timeout=4).close() for path in ('/', '/assets/css/app.css')]"]
