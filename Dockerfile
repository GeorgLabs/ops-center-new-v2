# Ops Center - production image.   Build: docker compose build     Run: docker compose up -d
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Only what the server needs at runtime (see .dockerignore for what stays out).
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY static ./static

# Never run as root. The database lives in /data (a volume), so the app directory can stay read-only.
RUN useradd --system --uid 10001 --no-create-home app && mkdir /data && chown app:app /data
USER app

# OPS_SECRET_KEY is NOT set here on purpose: secrets never go into an image. compose passes it in.
ENV OPS_DEV=0 \
    OPS_DATABASE_URL=sqlite:////data/opscenter.db

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"

# ONE worker on purpose: the login rate limiter keeps its counters in memory (see app/ratelimit.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
