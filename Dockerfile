# IT Department system (sign-in, forms page, staff portal, student diary, newsletter studio) as one web service.
# Build:  docker build -t it-portal .
# Run:    docker run -p 10000:10000 -v it-data:/data -e MASTER_SECRET=... -e MASTER_ADMIN_PASSWORD=... it-portal
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data \
    MASTER_DB_PATH=/data/master_system.db \
    NEWSLETTER_DB_PATH=/data/newsletter_system.db \
    PORT=10000

WORKDIR /app

# dependencies first, so a code change does not reinstall them
COPY requirements.txt .
RUN pip install -r requirements.txt

# the application (see .dockerignore for what is left out: databases, tests, generated files, local virtual environment)
COPY . .

# Runs as an ordinary user. The entrypoint starts as root only to fix the ownership of the mounted data disk
# (Render mounts it root-owned), then drops to this user before the server starts.
RUN useradd --system --home-dir /app app \
    && chmod +x /app/docker-entrypoint.sh

VOLUME ["/data"]
EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','10000'), timeout=4)" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# One worker on purpose: sign-in attempt limiting is kept in memory, and SQLite wants one writer. Plenty for a department.
CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
