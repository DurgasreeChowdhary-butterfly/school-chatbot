# School chatbot server. Build and start with: docker compose up -d --build   (see docs/deploy.md)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/chatbot.db \
    FORWARDED_ALLOW_IPS=127.0.0.1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY widget ./widget
COPY scripts ./scripts
# kb/ and config/ are copied as a fallback; docker-compose.yml mounts the live folders over them,
# so content can be replaced without rebuilding.
COPY kb ./kb
COPY config ./config

# Run as a normal user, not root. The database lives in /app/data (a volume).
RUN useradd --create-home --uid 1000 chatbot && mkdir -p /app/data && chown chatbot /app/data
USER chatbot

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

# One process only: staff logins and rate limits are kept in memory.
# --proxy-headers: behind Caddy, use the visitor's real IP address (for rate limits) and https (for secure cookies).
# Only the proxy in FORWARDED_ALLOW_IPS is believed (docker-compose.yml sets Caddy's fixed address). Never "*":
# then anyone reaching the app could fake their address and dodge the rate limit (tests/test_proxy_headers.py).
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
