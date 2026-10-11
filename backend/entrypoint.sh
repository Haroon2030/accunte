#!/bin/bash
set -e

echo "=== Starting Application ==="

# Wait for database to be ready
echo "Waiting for database..."
# محاولة اتصال واحدة كل 60 ثانية: الاستضافة تحدّد عدد الاتصالات في الساعة (max_connections_per_hour)،
# والانهيار وإعادة التشغيل السريعة كانت تستنزفها. التطبيق ينتظر بهدوء حتى تعود القاعدة.
until python manage.py shell -c "from django.db import connection; connection.ensure_connection()" >/dev/null 2>&1; do
    echo "Database not reachable yet; retrying in 60s..."
    sleep 60
done
echo "Database is reachable."

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Creating first admin (only if ADMIN_PASSWORD is provided) ==="
if [ -n "$ADMIN_PASSWORD" ]; then
python manage.py shell << 'EOF'
import os
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ.get('ADMIN_USERNAME', 'admin')
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username, os.environ.get('ADMIN_EMAIL', ''), os.environ['ADMIN_PASSWORD'])
    print('Superuser created')
else:
    print('Superuser exists (password untouched)')
EOF
else
    echo "ADMIN_PASSWORD not set: skipping admin creation"
fi

echo "=== Creating/updating system roles ==="
python manage.py setup_roles

echo "=== Mirroring legacy payment audit log (idempotent) ==="
python manage.py backfill_payment_audit

echo "=== Collecting static files ==="
python manage.py collectstatic --clear --noinput

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application -c gunicorn.conf.py
