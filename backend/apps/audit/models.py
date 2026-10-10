"""
سجل التدقيق غير القابل للتعديل - Immutable Audit Trail
"""
from django.conf import settings
from django.db import models


class ImmutableError(Exception):
    """يُرفع عند محاولة تعديل أو حذف سجل تدقيق."""


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableError('سجل التدقيق غير قابل للتعديل')

    def delete(self):
        raise ImmutableError('سجل التدقيق غير قابل للحذف')

    def bulk_update(self, *args, **kwargs):
        raise ImmutableError('سجل التدقيق غير قابل للتعديل')


class AuditLog(models.Model):
    """سجل واحد = إجراء واحد. يُكتب مرة واحدة ولا يُعدَّل أبدًا."""

    class Action(models.TextChoices):
        CREATE = 'create', 'إنشاء'
        UPDATE = 'update', 'تعديل'
        DELETE = 'delete', 'حذف'
        STATUS_CHANGE = 'status_change', 'تغيير حالة'
        APPROVAL = 'approval', 'قرار موافقة'
        AMOUNT_EDIT = 'amount_edit', 'تعديل مبلغ'
        IMPORT = 'import', 'استيراد'
        LOGIN = 'login', 'تسجيل دخول'
        LOGOUT = 'logout', 'تسجيل خروج'
        LOGIN_FAILED = 'login_failed', 'فشل تسجيل دخول'
        EXPORT = 'export', 'تصدير'
        OTHER = 'other', 'أخرى'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_trail', verbose_name='المنفذ',
    )
    # نسخة نصية تبقى حتى لو حُذف المستخدم
    actor_username = models.CharField('اسم المنفذ', max_length=150, blank=True)
    action = models.CharField('الإجراء', max_length=20, choices=Action.choices, db_index=True)
    entity_type = models.CharField('نوع السجل', max_length=100, db_index=True)
    entity_id = models.CharField('معرف السجل', max_length=64, blank=True, db_index=True)
    entity_repr = models.CharField('وصف السجل', max_length=300, blank=True)
    previous_state = models.JSONField('الحالة السابقة', null=True, blank=True)
    new_state = models.JSONField('الحالة الجديدة', null=True, blank=True)
    reason = models.TextField('سبب/مبرر', blank=True)
    ip_address = models.GenericIPAddressField('عنوان IP', null=True, blank=True)
    user_agent = models.CharField('المتصفح', max_length=300, blank=True)
    request_path = models.CharField('المسار', max_length=300, blank=True)
    created_at = models.DateTimeField('الوقت', auto_now_add=True, db_index=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        verbose_name = 'سجل تدقيق'
        verbose_name_plural = 'سجل التدقيق'
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['entity_type', 'entity_id', '-created_at'])]

    def __str__(self):
        return f'{self.get_action_display()} · {self.entity_type}#{self.entity_id}'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableError('سجل التدقيق غير قابل للتعديل')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableError('سجل التدقيق غير قابل للحذف')
