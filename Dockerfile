# =============================================
# AlphaFinder Production Dockerfile
# =============================================
FROM python:3.10-slim

# System dependencies for Prophet and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (for Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY . .

# Port (Render injects $PORT automatically)
EXPOSE 8000

# Production server: Gunicorn with Uvicorn workers
CMD ["gunicorn", "main:app", "-c", "gunicorn_config.py"]
