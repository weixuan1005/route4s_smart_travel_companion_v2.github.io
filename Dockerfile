# Backend + web app in one container, e.g. for Google Cloud Run.
# Secrets (LTA_ACCOUNT_KEY etc.) are passed as environment variables at deploy time, never baked in.
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY frontend frontend
COPY test_data test_data
ENV PORT=8080
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}
