import os
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

SLA_DAYS = 5


class User(AbstractUser):
    SUPPLIER, MATCHER, SUPERVISOR, MANAGER, ADMIN = 'supplier', 'matcher', 'supervisor', 'manager', 'admin'
    ROLES = [(SUPPLIER, 'مورد'), (MATCHER, 'مطابق'), (SUPERVISOR, 'مشرف الدعم'), (MANAGER, 'مدير مالي'), (ADMIN, 'مدير النظام')]

    first_name = None
    last_name = None
    name = models.CharField('الاسم الكامل', max_length=150)
    role = models.CharField(max_length=10, choices=ROLES, default=SUPPLIER)
    org = models.CharField('الجهة / اسم المورد', max_length=200, blank=True)
    code = models.CharField('رمز المورد', max_length=30, unique=True, null=True, blank=True)
    tax_no = models.CharField('الرقم الضريبي', max_length=15, blank=True)
    must_change_password = models.BooleanField(default=False)
    pages = models.JSONField('الصفحات المسموحة', null=True, blank=True)  # None = the role's default pages
    created_at = models.DateTimeField(default=timezone.now)

    REQUIRED_FIELDS = ['name']

    def __str__(self):
        return f'{self.name} ({self.username})'


def upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f'{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}'


class MatchRequest(models.Model):
    number = models.CharField(max_length=20, unique=True, null=True, editable=False)
    supplier = models.ForeignKey(User, on_delete=models.PROTECT, related_name='requests')
    period = models.CharField(max_length=60)
    notes = models.TextField(blank=True)
    stage = models.PositiveSmallIntegerField(default=1)  # 1 queue, 2 matching, 3 dialogue, 4 matched (awaiting the file), 5 file sent
    matcher = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned')
    diff = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    due_at = models.DateTimeField()
    reached = models.JSONField(default=dict)  # {"1": iso, "2": iso, ...}
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.number or f'#{self.pk}'


class Complaint(models.Model):
    number = models.CharField(max_length=20, unique=True, null=True, editable=False)
    supplier = models.ForeignKey(User, on_delete=models.PROTECT, related_name='complaints')
    category = models.CharField(max_length=80)
    subject = models.CharField(max_length=200)
    related = models.ForeignKey(MatchRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    stage = models.PositiveSmallIntegerField(default=1)  # 1 new, 2 under review, 3 replied
    reached = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.number or f'#{self.pk}'


class Message(models.Model):
    SUPPLIER, MATCHER, MANAGER, SYSTEM = 'supplier', 'matcher', 'manager', 'system'
    request = models.ForeignKey(MatchRequest, null=True, blank=True, on_delete=models.CASCADE, related_name='messages')
    complaint = models.ForeignKey(Complaint, null=True, blank=True, on_delete=models.CASCADE, related_name='messages')
    kind = models.CharField(max_length=10)
    sender = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [models.CheckConstraint(
            condition=(models.Q(request__isnull=False, complaint__isnull=True) | models.Q(request__isnull=True, complaint__isnull=False)),
            name='message_has_one_parent')]


class Attachment(models.Model):
    STATEMENT, CHAT, RESULT = 'statement', 'chat', 'result'
    file = models.FileField(upload_to=upload_path, max_length=300)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField()
    kind = models.CharField(max_length=10, default=CHAT)
    request = models.ForeignKey(MatchRequest, null=True, blank=True, on_delete=models.CASCADE, related_name='attachments')
    message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.CASCADE, related_name='files')
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(default=timezone.now)


@receiver(post_delete, sender=Attachment)
def remove_stored_file(sender, instance, **kwargs):
    """Deleting a record also removes its files from storage (disk or R2) once the deletion is committed."""
    name = instance.file.name
    if name:
        transaction.on_commit(lambda: instance.file.storage.delete(name))
