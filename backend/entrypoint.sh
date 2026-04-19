#!/bin/bash
set -e

echo "=== Starting Application ==="

# Wait for database to be ready
echo "Waiting for database..."
sleep 5

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Creating superuser if not exists ==="
python manage.py shell << 'EOF'
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@admin.com', '123456')
    print('Superuser created')
else:
    print('Superuser exists')
EOF

echo "=== Creating default roles if not exist ==="
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

echo "=== Updating template with new asset names ==="
python << 'EOF'
import os
import re
from pathlib import Path

STATIC_DIR = Path('/app/static/frontend')
TEMPLATE_FILE = Path('/app/templates/admin/frontend.html')

# Find the latest JS and CSS files
js_files = list(STATIC_DIR.glob('assets/index-*.js'))
css_files = list(STATIC_DIR.glob('assets/index-*.css'))

if js_files and css_files:
    # Get the most recent files
    js_file = sorted(js_files, key=lambda x: x.stat().st_mtime, reverse=True)[0].name
    css_file = sorted(css_files, key=lambda x: x.stat().st_mtime, reverse=True)[0].name
    
    if TEMPLATE_FILE.exists():
        content = TEMPLATE_FILE.read_text(encoding='utf-8')
        content = re.sub(r"{% static 'frontend/assets/index-[^']+\.js' %}", f"{{% static 'frontend/assets/{js_file}' %}}", content)
        content = re.sub(r"{% static 'frontend/assets/index-[^']+\.css' %}", f"{{% static 'frontend/assets/{css_file}' %}}", content)
        TEMPLATE_FILE.write_text(content, encoding='utf-8')
        print(f"Updated template: JS={js_file}, CSS={css_file}")
    else:
        print("Template file not found")
else:
    print("No asset files found")
EOF

echo "=== Collecting static files ==="
python manage.py collectstatic --noinput

echo "=== Starting Gunicorn ==="
exec gunicorn config.wsgi:application --bind 0.0.0.0:8096 --workers 3 --timeout 120
