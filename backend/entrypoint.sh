#!/bin/bash
set -e

echo "=== Starting Application ==="

# محاولة اتصال واحدة كل 60 ثانية: الاستضافة قد تحدّد عدد الاتصالات في الساعة،
# والانهيار السريع وإعادة التشغيل كانا يستنزفانها. ينتظر التطبيق بهدوء حتى تعود القاعدة.
echo "Waiting for database..."
until python manage.py shell -c "from django.db import connection; connection.ensure_connection()" >/dev/null 2>&1; do
    echo "Database not reachable yet; retrying in 60s..."
    sleep 60
done
echo "Database is reachable."

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Creating first admin (needs ADMIN_PASSWORD; safe to repeat) ==="
python manage.py bootstrap_admin

echo "=== Collecting static files (includes the frontend) ==="
python manage.py collectstatic --clear --noinput

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application -c gunicorn.conf.py
