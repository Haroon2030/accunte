#!/bin/bash
set -e

echo "=== Fixing migration history ==="
python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
try:
    cursor.execute('DELETE FROM django_migrations')
    print('Cleared migration history')
except Exception as e:
    print(f'No migration table yet: {e}')
"

echo "=== Faking migrations (tables already exist) ==="
python manage.py migrate --fake --noinput

echo "=== Creating superuser ==="
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@admin.com', '123456')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
"

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application --bind 0.0.0.0:8096 --workers 3 --timeout 120
