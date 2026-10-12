FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DJANGO_ENV=production
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend

WORKDIR /app/backend
RUN SECRET_KEY=build-only DJANGO_ENV=development python manage.py collectstatic --noinput

EXPOSE 8096
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8096/healthz', timeout=4).status == 200 else 1)"

# wait for the database, clear the old app's tables once, migrate, create first accounts, then serve
CMD ["sh", "-c", "until python manage.py wipe_legacy_database && python manage.py migrate --noinput && python manage.py bootstrap_users; do echo 'database not ready, retrying in 30s'; sleep 30; done; exec gunicorn config.wsgi --bind 0.0.0.0:8096 --workers 2 --threads 2 --timeout 120 --access-logfile -"]
