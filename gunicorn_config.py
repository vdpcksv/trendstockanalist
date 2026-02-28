# =============================================
# AlphaFinder Gunicorn Production Config
# =============================================
import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Worker Processes
# Render Free tier: 1 worker | Paid tier: 2-4 workers
workers = int(os.getenv("WEB_CONCURRENCY", min(2, multiprocessing.cpu_count())))
worker_class = "uvicorn.workers.UvicornWorker"

# Timeout (60s for slow AI/scraping endpoints)
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")

# Process naming
proc_name = "alphafinder"

# Preload app for memory efficiency
preload_app = True
