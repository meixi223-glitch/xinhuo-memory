FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 MEMORY_STATE_DIR=/data MEMORY_HOST=0.0.0.0 MEMORY_PORT=18200 AFFECT_INTAKE_MODE=self_report
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 10001 xinhuo && useradd -u 10001 -g xinhuo -M xinhuo && mkdir /data && chown xinhuo:xinhuo /data
COPY xinhuo/ ./xinhuo/
COPY scripts/ ./scripts/
COPY --from=frontend /build/dist ./frontend/dist
USER xinhuo
VOLUME /data
EXPOSE 18200
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18200/health',timeout=3)"
CMD ["python", "xinhuo/room_runtime.py"]
