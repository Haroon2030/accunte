#!/bin/bash
set -e

echo "=== Starting Application ==="

# Wait for database
sleep 3

echo "=== Fixing database schema ==="
python manage.py shell << 'PYEOF'
from django.db import connection
cursor = connection.cursor()

def column_exists(table, column):
    cursor.execute(f"SHOW COLUMNS FROM {table} LIKE '{column}'")
    return cursor.fetchone() is not None

def add_column(table, column, definition):
    if not column_exists(table, column):
        print(f"Adding {table}.{column}...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return True
    return False

try:
    # Fix core_userprofile table
    print("Checking core_userprofile...")
    add_column("core_userprofile", "branch_id", "bigint NULL")
    add_column("core_userprofile", "role_id", "bigint NULL")
    add_column("core_userprofile", "phone", "varchar(20) DEFAULT ''")
    add_column("core_userprofile", "department", "varchar(100) DEFAULT ''")
    add_column("core_userprofile", "position", "varchar(100) DEFAULT ''")
    add_column("core_userprofile", "avatar", "varchar(100) DEFAULT ''")
    add_column("core_userprofile", "is_protected", "tinyint(1) DEFAULT 0")
    
    # Fix core_role table
    print("Checking core_role...")
    add_column("core_role", "role_type", "varchar(20) DEFAULT 'branch_employee'")
    add_column("core_role", "is_system_role", "tinyint(1) DEFAULT 0")
    
    connection.commit()
    print("Schema fixes completed!")
    
    # Clear core migration records
    cursor.execute("DELETE FROM django_migrations WHERE app='core'")
    connection.commit()
    print("Cleared core migration records")
    
except Exception as e:
    print(f"Error: {e}")
    connection.rollback()
PYEOF

# Fake all migrations since we fixed schema manually
python manage.py migrate --fake --noinput

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
