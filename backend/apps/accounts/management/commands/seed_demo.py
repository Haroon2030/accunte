"""
حسابات وبيانات تجريبية للتطوير المحلي فقط (يرفض العمل إذا DEBUG=False).
كلمات المرور هنا للتجربة المحلية وحدها، وتُعامل كحسابات عادية (لا تغيير إلزامي).
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import UserProfile

DEMO = [
    ('admin', 'مدير النظام', 'admin', 'أسواق الراشد'),
    ('salman', 'سلمان القحطاني', 'manager', 'الإدارة المالية'),
    ('khaled', 'خالد العتيبي', 'matcher', 'قسم المطابقة'),
    ('mona', 'منى الدوسري', 'matcher', 'قسم المطابقة'),
    ('nokhba', 'مسؤول شركة النخبة', 'supplier', 'شركة النخبة للتوريدات'),
    ('fajr', 'مسؤول مصنع الفجر', 'supplier', 'مصنع الفجر للتغليف'),
]
PASSWORD = 'Demo@12345'


class Command(BaseCommand):
    help = 'ينشئ حسابات تجريبية للتطوير المحلي (DEBUG فقط)'

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError('seed_demo للتطوير المحلي فقط.')
        User = get_user_model()
        for username, name, role, org in DEMO:
            user, created = User.objects.get_or_create(username=username, defaults={'first_name': name, 'is_staff': role == 'admin', 'is_superuser': role == 'admin'})
            if created:
                user.set_password(PASSWORD)
                user.save()
            UserProfile.objects.update_or_create(user=user, defaults={'role': role, 'org': org, 'must_change_password': False})
        self.stdout.write(self.style.SUCCESS(f'جاهزة {len(DEMO)} حسابات تجريبية (كلمة المرور في هذا الملف).'))
