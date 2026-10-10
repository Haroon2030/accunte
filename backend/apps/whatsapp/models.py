"""
صندوق واتساب المشترك: المحادثات والرسائل وإسناد الموظفين وإعداد SLA.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class SLAConfiguration(models.Model):
    """أهداف زمن الاستجابة. صف واحد افتراضي يُنشأ عند أول استخدام."""
    name = models.CharField('الاسم', max_length=60, unique=True, default='default')
    first_response_minutes = models.PositiveIntegerField('مهلة الرد الأول (دقيقة)', default=30)
    resolution_hours = models.PositiveIntegerField('مهلة الإغلاق (ساعة)', default=24)

    class Meta:
        verbose_name = 'إعداد SLA'
        verbose_name_plural = 'إعدادات SLA'

    def __str__(self):
        return self.name

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(name='default')
        return obj


class SupplierConversation(models.Model):
    """محادثة واحدة لكل رقم واتساب. تُعاد فتحها عند وصول رسالة جديدة بعد الإغلاق."""

    class Status(models.TextChoices):
        NEW = 'new', 'جديدة'
        OPEN = 'open', 'مفتوحة'
        PENDING = 'pending', 'بانتظار العميل'
        ESCALATED = 'escalated', 'مصعَّدة'
        CLOSED = 'closed', 'مغلقة'

    contact_number = models.CharField('رقم الواتساب', max_length=20, unique=True)
    display_name = models.CharField('الاسم الظاهر', max_length=150, blank=True)
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='conversations', verbose_name='المورد')
    contact = models.ForeignKey('suppliers.SupplierContact', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='+', verbose_name='جهة الاتصال')
    reconciliation_case = models.ForeignKey('reconciliation.ReconciliationCase', on_delete=models.SET_NULL,
                                            null=True, blank=True, related_name='conversations',
                                            verbose_name='حالة المطابقة المرتبطة')
    status = models.CharField('الحالة', max_length=10, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='whatsapp_conversations', verbose_name='الموظف المسؤول')
    version = models.PositiveIntegerField('إصدار القفل التفاؤلي', default=0)
    unread_count = models.PositiveIntegerField('غير المقروءة', default=0)
    awaiting_reply_since = models.DateTimeField('بانتظار رد منذ', null=True, blank=True, db_index=True)
    last_message_at = models.DateTimeField('آخر رسالة', null=True, blank=True, db_index=True)
    last_response_seconds = models.PositiveIntegerField('آخر زمن استجابة (ث)', null=True, blank=True)
    # قفل ناعم لتنبيه الموظفين الآخرين: من يكتب الآن
    typing_agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='+')
    typing_until = models.DateTimeField(null=True, blank=True)
    escalation_reason = models.TextField('سبب التصعيد', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'محادثة مورد'
        verbose_name_plural = 'محادثات الموردين'
        ordering = ['-last_message_at', '-id']
        indexes = [
            models.Index(fields=['status', '-last_message_at']),
            models.Index(fields=['assigned_agent', 'status']),
        ]

    def __str__(self):
        return f'{self.display_name or self.contact_number}'

    @property
    def is_unanswered_overdue(self):
        if not self.awaiting_reply_since or self.status == self.Status.CLOSED:
            return False
        limit = SLAConfiguration.current().first_response_minutes
        return (timezone.now() - self.awaiting_reply_since).total_seconds() > limit * 60

    @property
    def waiting_minutes(self):
        if not self.awaiting_reply_since:
            return 0
        return int((timezone.now() - self.awaiting_reply_since).total_seconds() // 60)


class ConversationMessage(models.Model):

    class Direction(models.TextChoices):
        IN = 'in', 'وارد'
        OUT = 'out', 'صادر'

    class Kind(models.TextChoices):
        TEXT = 'text', 'نص'
        IMAGE = 'image', 'صورة'
        AUDIO = 'audio', 'صوت'
        VIDEO = 'video', 'فيديو'
        DOCUMENT = 'document', 'مستند'
        STICKER = 'sticker', 'ملصق'
        OTHER = 'other', 'أخرى'

    class DeliveryStatus(models.TextChoices):
        PENDING = 'pending', 'قيد الإرسال'
        SENT = 'sent', 'أُرسلت'
        DELIVERED = 'delivered', 'وصلت'
        READ = 'read', 'قُرئت'
        FAILED = 'failed', 'فشلت'
        RECEIVED = 'received', 'مستلمة'

    conversation = models.ForeignKey(SupplierConversation, on_delete=models.CASCADE, related_name='messages')
    direction = models.CharField(max_length=3, choices=Direction.choices)
    wa_message_id = models.CharField('معرّف رسالة واتساب', max_length=128, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEXT)
    body = models.TextField('النص', blank=True)
    media_name = models.CharField(max_length=255, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='+')
    status = models.CharField(max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.RECEIVED)
    error = models.CharField(max_length=300, blank=True)
    response_seconds = models.PositiveIntegerField(null=True, blank=True)
    timestamp = models.DateTimeField('وقت الرسالة', default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'رسالة'
        verbose_name_plural = 'الرسائل'
        ordering = ['timestamp', 'id']
        constraints = [
            # منع تكرار الرسالة نفسها إذا أعاد Evolution إرسال الحدث (Idempotency)
            models.UniqueConstraint(fields=['wa_message_id'], condition=~Q(wa_message_id=''),
                                    name='uniq_whatsapp_message_id'),
        ]
        indexes = [models.Index(fields=['conversation', 'timestamp'])]

    def __str__(self):
        return f'{self.get_direction_display()}: {self.body[:30]}'


class ConversationAssignment(models.Model):
    """سجل الإسنادات: من تولّى المحادثة ومتى."""
    conversation = models.ForeignKey(SupplierConversation, on_delete=models.CASCADE, related_name='assignments')
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'إسناد محادثة'
        verbose_name_plural = 'إسنادات المحادثات'
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(fields=['conversation'], condition=Q(is_active=True),
                                    name='one_active_conversation_assignment'),
        ]
