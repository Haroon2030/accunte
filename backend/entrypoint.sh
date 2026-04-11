#!/bin/bash
set -e

echo "=== Starting Application ==="

# Wait for database
sleep 3

echo "=== Running migrations ==="
# Use --fake-initial to handle tables that already exist
python manage.py migrate --fake-initial --noinput || {
    echo "Migration error, trying --fake..."
    python manage.py migrate --fake --noinput
}

echo "=== Creating superuser ==="
python manage.py shell << 'EOF'
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@admin.com', '123456')
    print('Superuser created')
else:
    print('Superuser exists')
EOF

echo "=== Creating default roles ==="
python manage.py shell << 'EOF'
from apps.core.models import Role

roles = [
    {'name': 'مدير النظام', 'role_type': 'admin', 'description': 'صلاحيات كاملة'},
    {'name': 'مدير', 'role_type': 'manager', 'description': 'إدارة الطلبات'},
    {'name': 'مدقق', 'role_type': 'auditor', 'description': 'مراجعة الطلبات'},
    {'name': 'موظف فرع', 'role_type': 'branch_employee', 'description': 'إنشاء طلبات'},
]

for r in roles:
    obj, created = Role.objects.get_or_create(
        name=r['name'],
        defaults={'role_type': r['role_type'], 'description': r['description'], 'is_system_role': True}
    )
    print(f"{'Created' if created else 'Exists'}: {r['name']}")
EOF

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application --bind 0.0.0.0:8096 --workers 3 --timeout 120
