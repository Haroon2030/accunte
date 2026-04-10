"""
إعداد الأدوار الأساسية
python manage.py setup_roles
"""
from django.core.management.base import BaseCommand
from apps.core.models import Role


class Command(BaseCommand):
    help = 'إنشاء وتحديث الأدوار الأساسية في النظام'

    def handle(self, *args, **options):
        # أولاً: تحديث الأدوار الموجودة بالاسم
        existing_roles_update = {
            'مدير النظام': {'role_type': 'admin', 'is_system_role': True, 'description': 'صلاحيات كاملة على النظام - لا يمكن تعديله أو حذفه'},
        }
        
        for name, data in existing_roles_update.items():
            try:
                role = Role.objects.get(name=name)
                role.role_type = data['role_type']
                role.is_system_role = data['is_system_role']
                role.description = data['description']
                role.save()
                self.stdout.write(self.style.WARNING(f'تم تحديث الدور الموجود: {name}'))
            except Role.DoesNotExist:
                pass
        
        # ثانياً: إنشاء الأدوار المفقودة
        roles_to_create = [
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

        for role_data in roles_to_create:
            # تحقق من وجود الدور بنوعه
            existing_roles = Role.objects.filter(role_type=role_data['role_type'])
            if not existing_roles.exists():
                Role.objects.create(**role_data)
                self.stdout.write(self.style.SUCCESS(f'تم إنشاء الدور: {role_data["name"]}'))
            else:
                # تحديث أول دور موجود ووضعه كدور نظام
                role = existing_roles.first()
                role.is_system_role = role_data['is_system_role']
                if not role.description:
                    role.description = role_data['description']
                role.save()
                self.stdout.write(self.style.WARNING(f'الدور موجود: {role.name}'))

        self.stdout.write(self.style.SUCCESS('تم إعداد الأدوار بنجاح!'))
