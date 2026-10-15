# 1. The web UI (frontend/): React + Vite, built into backend/web.
FROM node:24.19.0-slim AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend ./
# Nightjar's pixel bird: one drawing shared with the CLI (a frontend test checks the copies match)
COPY backend/watch/nightjar.json /src/backend/watch/nightjar.json
RUN npm run build

# 2. The app: FastAPI serving the API and the built UI.
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY cli ./cli
COPY --from=web /src/backend/web ./backend/web
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# Seed on boot: the free cloud tier keeps no data, so every start rebuilds the graphs.
# Free-tier armour: a slow LLM can't hold a worker for long, and past 64 open connections the server answers
# 503 at once instead of queueing until it falls over. Visitor addresses come from limits.visitor().
ENV LLM_TIMEOUT=20
# Render (and most hosts) put one proxy in front; docker-compose, with none, sets 0.
ENV CHOKEPOINT_TRUSTED_PROXIES=1
CMD ["sh", "-c", "python backend/scripts/seed.py && uvicorn chokepoint.api.app:app --host 0.0.0.0 --port ${PORT:-8000} --limit-concurrency 64 --timeout-keep-alive 5"]
