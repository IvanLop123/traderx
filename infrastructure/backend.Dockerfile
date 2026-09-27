FROM python:3.12-slim
WORKDIR /app
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt
COPY backend backend
COPY scripts/provider_common.py scripts/provider_common.py
COPY config config
COPY migrations migrations
COPY alembic.ini .env.example ./
RUN mkdir -p data
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
