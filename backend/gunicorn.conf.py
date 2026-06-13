"""Gunicorn production settings."""
import os

bind = '0.0.0.0:8096'
workers = int(os.environ.get('GUNICORN_WORKERS', 2))
worker_class = 'gthread'
threads = int(os.environ.get('GUNICORN_THREADS', 2))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))
graceful_timeout = 30
keepalive = 5
max_requests = 500
max_requests_jitter = 50
accesslog = '-'
errorlog = '-'
loglevel = 'info'
