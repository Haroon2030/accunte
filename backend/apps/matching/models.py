import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .storage import private_storage

SLA_DAYS = 5


def upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    return f'matching/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{ext[:8]}'


def empty_reached():
    return [None] * 5


class MatchRequest(models.Model):
    """طلب مطابقة كشف حساب. المراحل: 1 تقديم، 2 مطابقة، 3 مراسلات واستيضاح، 4 إنجاز (كما في الواجهة)."""
    code = models.CharField('الرقم', max_length=20, unique=True, null=True, blank=True, editable=False)
    supplier_org = models.CharField('المورد', max_length=150, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='match_requests')
    period = models.CharField('الفترة', max_length=100)
    notes = models.TextField('ملاحظات', blank=True)
    stage = models.PositiveSmallIntegerField('المرحلة', default=1)
    matcher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='assigned_requests')
    diff = models.DecimalField('الفرق المبدئي', max_digits=16, decimal_places=2, null=True, blank=True)
    reached = models.JSONField('أوقات بلوغ المراحل', default=empty_reached)
    created_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'طلب مطابقة'
        verbose_name_plural = 'طلبات المطابقة'
        indexes = [models.Index(fields=['stage', 'matcher'])]

    def __str__(self):
        return self.code or f'MT-{self.pk}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:                         # من المفتاح الأساسي: فريد بلا سباق تزامن
            self.code = f'MT-{self.created_at:%y%m}-{self.pk:04d}'
            super().save(update_fields=['code'])


class Complaint(models.Model):
    """شكوى تصل إلى المدير المالي مباشرة. المراحل: 1 تقديم، 2 وصلت المدير، 3 قيد المراجعة، 4 رد وإغلاق."""
    code = models.CharField('الرقم', max_length=20, unique=True, null=True, blank=True, editable=False)
    supplier_org = models.CharField('المورد', max_length=150, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='complaints')
    category = models.CharField('النوع', max_length=80)
    subject = models.CharField('العنوان', max_length=200)
    related = models.ForeignKey(MatchRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints')
    stage = models.PositiveSmallIntegerField('المرحلة', default=1)
    reached = models.JSONField(default=empty_reached)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'شكوى'
        verbose_name_plural = 'الشكاوى'

    def __str__(self):
        return self.code or f'SH-{self.pk}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:
            self.code = f'SH-{self.created_at:%y%m}-{self.pk:04d}'
            super().save(update_fields=['code'])


class Message(models.Model):
    """رسالة في مراسلات طلب أو شكوى (واحد منهما فقط)."""

    class Sender(models.TextChoices):
        SUPPLIER = 'supplier', 'المورد'
        MATCHER = 'matcher', 'المطابق'
        MANAGER = 'manager', 'المدير المالي'
        SYSTEM = 'system', 'النظام'

    request = models.ForeignKey(MatchRequest, on_delete=models.CASCADE, null=True, blank=True, related_name='messages')
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, null=True, blank=True, related_name='messages')
    sender_role = models.CharField(max_length=10, choices=Sender.choices)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(request__isnull=False, complaint__isnull=True)
                           | models.Q(request__isnull=True, complaint__isnull=False)),
                name='message_belongs_to_one_conversation'),
        ]


class Attachment(models.Model):
    """مرفق: كشف الحساب لطلب (statement_of) أو ملف في رسالة (message)."""
    statement_of = models.OneToOneField(MatchRequest, on_delete=models.CASCADE, null=True, blank=True,
                                        related_name='statement')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, null=True, blank=True, related_name='attachments')
    file = models.FileField(upload_to=upload_path, storage=private_storage)
    name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class Seen(models.Model):
    """آخر مرة فتح فيها المستخدم مراسلة (لعدّاد الرسائل غير المقروءة). المفتاح «الرقم:الدور»."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    key = models.CharField(max_length=60)
    at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'key'], name='seen_unique_per_user_key')]
