FROM python:3.12-slim

# libpq-dev + gcc required by psycopg2-binary build fallback on some archs
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package metadata first (layer cache friendly)
COPY pyproject.toml .

# Copy source
COPY ingestion/ ingestion/
COPY scheduler.py .

# Install package with all dependencies
RUN pip install --no-cache-dir -e .

EXPOSE 8080

CMD ["python", "scheduler.py"]
