from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """دور المستخدم وجهته. الاسم الكامل في first_name، وآخر دخول في last_login."""

    class Role(models.TextChoices):
        SUPPLIER = 'supplier', 'مورد'
        MATCHER = 'matcher', 'مطابق'
        MANAGER = 'manager', 'مدير مالي'
        ADMIN = 'admin', 'مدير النظام'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField('الدور', max_length=10, choices=Role.choices, default=Role.SUPPLIER)
    org = models.CharField('الجهة', max_length=150, blank=True)
    must_change_password = models.BooleanField('يجب تغيير كلمة المرور', default=False)
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'ملف مستخدم'
        verbose_name_plural = 'ملفات المستخدمين'

    def __str__(self):
        return f'{self.user.get_username()} ({self.role})'

    @property
    def is_staff_role(self):
        return self.role != self.Role.SUPPLIER
