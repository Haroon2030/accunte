"""
إنشاء الأدوار الافتراضية
"""
from django.db import migrations


def create_default_roles(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    
    # إنشاء الأدوار الأساسية
    roles_data = [
        {
            'name': 'مدير النظام',
            'role_type': 'admin',
            'description': 'صلاحيات كاملة على النظام - لا يمكن تعديله أو حذفه',
            'is_system_role': True,
        },
        {
            'name': 'مدير',
            'role_type': 'manager',
            'description': 'يمكنه رؤية جميع البيانات والتقارير',
            'is_system_role': True,
        },
        {
            'name': 'مدقق',
            'role_type': 'auditor',
            'description': 'يمكنه تغيير حالة التدقيق في الطلبات فقط',
            'is_system_role': True,
        },
        {
            'name': 'موظف فرع',
            'role_type': 'branch_employee',
            'description': 'يرى فقط البيانات المتعلقة بفرعه',
            'is_system_role': True,
        },
    ]
    
    for role_data in roles_data:
        # البحث عن دور موجود بهذا النوع أو الاسم
        existing_role = Role.objects.filter(role_type=role_data['role_type']).first()
        if not existing_role:
            existing_role = Role.objects.filter(name=role_data['name']).first()
        
        if existing_role:
            # تحديث الدور الموجود
            existing_role.role_type = role_data['role_type']
            existing_role.description = role_data['description']
            existing_role.is_system_role = role_data['is_system_role']
            existing_role.save()
        else:
            # إنشاء دور جديد
            Role.objects.create(**role_data)


def reverse_migration(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_role_is_system_role_role_role_type_and_more'),
    ]

    operations = [
        migrations.RunPython(create_default_roles, reverse_migration),
    ]
