"""
ينشئ مدير النظام الأول من متغيرات البيئة (آمن للتكرار):
  ADMIN_USERNAME (الافتراضي admin)، ADMIN_PASSWORD، ADMIN_NAME.
- مستخدم جديد: يُنشأ بكلمة المرور من البيئة ويُطلب منه تغييرها عند أول دخول.
- مستخدم موجود بلا ملف: يُنشأ له ملف مدير نظام دون المساس بكلمة مروره.
- مستخدم له ملف: لا يُغيَّر شيء (إلا مع --reset-password).
- أي سوبر يوزر موجود بلا ملف (كحسابات قاعدة الإنتاج القديمة) يُمنح ملف «مدير النظام» تلقائياً
  فيدخل بكلمة مروره الحالية دون تعديل يدوي.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import UserProfile
from apps.accounts.services import normalize_username, password_error


class Command(BaseCommand):
    help = 'ينشئ مدير النظام الأول من ADMIN_USERNAME / ADMIN_PASSWORD'

    def add_arguments(self, parser):
        parser.add_argument('--reset-password', action='store_true', help='يعيد تعيين كلمة مرور المدير من البيئة')

    def handle(self, *args, **opts):
        User = get_user_model()
        promoted = 0
        for su in User.objects.filter(is_superuser=True, is_active=True, profile__isnull=True):
            UserProfile.objects.create(user=su, role=UserProfile.Role.ADMIN, org='أسواق الراشد')
            promoted += 1
            self.stdout.write(f'مُنح السوبر يوزر «{su.get_username()}» ملف مدير النظام.')
        username = normalize_username(os.environ.get('ADMIN_USERNAME', 'admin'))
        password = os.environ.get('ADMIN_PASSWORD', '')
        name = os.environ.get('ADMIN_NAME', 'مدير النظام')
        user = User.objects.filter(username=username).first()
        if user is None:
            if not password:
                self.stdout.write('ADMIN_PASSWORD غير مضبوط: لا مدير جديد.')
                return
            err = password_error(password)
            if err:
                self.stderr.write(f'ADMIN_PASSWORD مرفوضة: {err}')
                return
            user = User.objects.create_user(username, password=password, first_name=name, is_staff=True, is_superuser=True)
            UserProfile.objects.create(user=user, role=UserProfile.Role.ADMIN, org='أسواق الراشد', must_change_password=True)
            self.stdout.write(f'أُنشئ مدير النظام «{username}» (يغيّر كلمة المرور عند أول دخول).')
            return
        profile, created = UserProfile.objects.get_or_create(
            user=user, defaults={'role': UserProfile.Role.ADMIN, 'org': 'أسواق الراشد'})
        if created:
            self.stdout.write(f'أُنشئ ملف مدير نظام للمستخدم الموجود «{username}».')
        if opts['reset_password'] and password and not password_error(password):
            user.set_password(password)
            user.save(update_fields=['password'])
            profile.must_change_password = True
            profile.save(update_fields=['must_change_password'])
            self.stdout.write('أُعيد تعيين كلمة المرور.')
        elif not created:
            self.stdout.write(f'المدير «{username}» موجود، لم يتغير شيء.')
