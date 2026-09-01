FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Persisted via the backend_storage volume in docker-compose.yml - this just
# makes sure the directory exists on first boot before any upload happens.
RUN mkdir -p /app/storage/documents

EXPOSE 8000

# app/seed.py is idempotent (each seed is skipped if it already exists - see
# its own docstring), so it's safe to run on every container start rather
# than requiring a separate manual bootstrap step.
CMD ["sh", "-c", "python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
