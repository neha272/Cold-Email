"""Gunicorn configuration for production deployment."""

import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
backlog = 2048

# Worker processes
# Formula: (2 x CPU cores) + 1 for optimal performance
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "cold-emailer"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Graceful timeout for worker restarts
graceful_timeout = 30

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("🚀 Cold Email Campaign Manager - Web Interface")
    server.log.info(f"📍 Server running at: http://0.0.0.0:{os.environ.get('PORT', '5000')}")
    server.log.info(f"👷 Workers: {workers}")
    server.log.info("✅ Production server (Gunicorn) ready")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("👋 Shutting down gracefully...")
