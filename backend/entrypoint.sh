#!/bin/bash
set -e

echo "=== Checking and fixing migrations ==="
# Check if core_role table exists, if not - reset and reapply migrations
python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
try:
    cursor.execute('SELECT 1 FROM core_role LIMIT 1')
    print('core_role table exists')
except:
    print('core_role table missing - resetting migrations')
    # Delete migration records for core app
    cursor.execute(\"DELETE FROM django_migrations WHERE app='core'\")
    connection.commit()
    print('Migration records cleared for core app')
"

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Ensuring superuser exists ==="
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@admin.com', '123456')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
"

echo "=== Creating default roles ==="
python manage.py shell -c "
from apps.core.models import Role

default_roles = [
    {'name': 'مدير النظام', 'role_type': 'admin', 'description': 'صلاحيات كاملة على النظام'},
    {'name': 'مدير', 'role_type': 'manager', 'description': 'إدارة الطلبات والموافقات'},
    {'name': 'مدقق', 'role_type': 'auditor', 'description': 'مراجعة وتدقيق الطلبات'},
    {'name': 'موظف فرع', 'role_type': 'branch_employee', 'description': 'إنشاء طلبات الدفع'},
]

for role_data in default_roles:
    role, created = Role.objects.get_or_create(
        name=role_data['name'],
        defaults={
            'role_type': role_data['role_type'],
            'description': role_data['description'],
            'is_system_role': True
        }
    )
    if created:
        print(f'Created role: {role.name}')
    else:
        print(f'Role exists: {role.name}')
"

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application --bind 0.0.0.0:8096 --workers 3 --timeout 120
