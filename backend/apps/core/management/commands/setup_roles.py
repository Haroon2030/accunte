"""
إعداد الأدوار الأساسية
python manage.py setup_roles
"""
from django.core.management.base import BaseCommand

from apps.core.models import Role

SYSTEM_ROLES = [
    ('مدير النظام', 'admin', 'صلاحيات كاملة على النظام - لا يمكن تعديله أو حذفه'),
    ('المدير المالي', 'cfo', 'الإشراف التنفيذي واعتماد مقترحات الدفع وصرفها ولوحة المؤشرات'),
    ('مشرف الدعم', 'cs_supervisor', 'إدارة صندوق واتساب وطلبات الخدمة وتوزيعها على المطابقين'),
    ('مطابق', 'accountant', 'تنفيذ المهام وحالات المطابقة المسندة إليه فقط'),
    ('مورد', 'supplier', 'حساب مورد: يدخل بوابة الموردين فقط لطلب الخدمات ومتابعتها'),
]


class Command(BaseCommand):
    help = 'إنشاء وتحديث الأدوار الأساسية في النظام'

    def handle(self, *args, **options):
        for name, role_type, description in SYSTEM_ROLES:
            role = Role.objects.filter(role_type=role_type).first() or Role.objects.filter(name=name).first()
            if role is None:
                Role.objects.create(name=name, role_type=role_type, description=description, is_system_role=True)
                self.stdout.write(self.style.SUCCESS(f'تم إنشاء الدور: {name}'))
                continue
            role.role_type = role_type
            role.is_system_role = True
            if not role.description:
                role.description = description
            role.save()
            self.stdout.write(self.style.WARNING(f'الدور موجود: {role.name}'))
        self.stdout.write(self.style.SUCCESS('تم إعداد الأدوار بنجاح!'))
