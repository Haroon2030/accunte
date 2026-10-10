"""
طلبات الخدمة: أنواع قابلة للتعريف، طلبات، مستندات، مواعيد، وسجل حالات.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Role
from apps.reconciliation.models import document_upload_path
from apps.reconciliation.storage import private_storage

RT = Role.RoleType
DEFAULT_CREATE_ROLES = [RT.ADMIN, RT.CFO, RT.MANAGER, RT.CS_SUPERVISOR, RT.CS_AGENT, RT.ACCOUNTANT]


class ServiceType(models.Model):
    """نوع خدمة. الحقول والمستندات والمهلة والتصعيد والصلاحيات كلها قابلة للضبط من الإدارة."""
    code = models.SlugField('الرمز', max_length=40, unique=True)
    name = models.CharField('الاسم', max_length=120)
    description = models.TextField('الوصف', blank=True)
    destination_role = models.CharField('الجهة المستلمة (دور)', max_length=20, choices=RT.choices,
                                        default=RT.CS_AGENT)
    sla_hours = models.PositiveIntegerField('مهلة الإنجاز (ساعة)', default=24)
    escalation_role = models.CharField('جهة التصعيد (دور)', max_length=20, choices=RT.choices,
                                       default=RT.CS_SUPERVISOR)
    field_schema = models.JSONField('الحقول المطلوبة', default=list, blank=True)
    required_documents = models.JSONField('المستندات الإلزامية', default=list, blank=True)
    create_roles = models.JSONField('الأدوار التي تنشئ الطلب', default=list, blank=True)
    handle_roles = models.JSONField('الأدوار التي تعالج الطلب', default=list, blank=True)
    spawns_reconciliation = models.BooleanField('يُنشئ حالة مطابقة', default=False)
    whatsapp_menu = models.BooleanField('يظهر في قائمة واتساب الآلية', default=True)
    is_active = models.BooleanField('فعّال', default=True)
    sort_order = models.PositiveIntegerField('الترتيب', default=100)

    class Meta:
        verbose_name = 'نوع خدمة'
        verbose_name_plural = 'أنواع الخدمات'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def effective_create_roles(self):
        return list(self.create_roles or DEFAULT_CREATE_ROLES)

    def effective_handle_roles(self):
        base = list(self.handle_roles or [])
        for r in (self.destination_role, RT.CS_SUPERVISOR, RT.MANAGER):
            if r not in base:
                base.append(r)
        return base


class ServiceRequest(models.Model):

    class Status(models.TextChoices):
        NEW = 'new', 'جديد'
        IN_PROGRESS = 'in_progress', 'قيد المعالجة'
        WAITING_VENDOR = 'waiting_vendor', 'بانتظار المورد'
        ESCALATED = 'escalated', 'مصعَّد'
        RESOLVED = 'resolved', 'تم الحل'
        CLOSED = 'closed', 'مغلق'
        CANCELLED = 'cancelled', 'ملغى'

    class Priority(models.TextChoices):
        LOW = 'low', 'منخفضة'
        NORMAL = 'normal', 'عادية'
        HIGH = 'high', 'عالية'
        URGENT = 'urgent', 'عاجلة'

    class Source(models.TextChoices):
        STAFF = 'staff', 'موظف'
        WHATSAPP = 'whatsapp', 'واتساب (آلي)'

    TERMINAL = (Status.CLOSED, Status.CANCELLED)
    OPEN = (Status.NEW, Status.IN_PROGRESS, Status.WAITING_VENDOR, Status.ESCALATED)

    reference = models.CharField('الرقم المرجعي', max_length=30, unique=True, null=True, blank=True, editable=False)
    service_type = models.ForeignKey(ServiceType, on_delete=models.PROTECT, related_name='requests', verbose_name='النوع')
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT, related_name='service_requests',
                                 verbose_name='المورد')
    conversation = models.ForeignKey('whatsapp.SupplierConversation', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='service_requests', verbose_name='المحادثة')
    reconciliation_case = models.ForeignKey('reconciliation.ReconciliationCase', on_delete=models.SET_NULL, null=True,
                                            blank=True, related_name='service_requests', verbose_name='حالة المطابقة')
    subject = models.CharField('الموضوع', max_length=200)
    details = models.TextField('التفاصيل', blank=True)
    data = models.JSONField('بيانات الحقول', default=dict, blank=True)
    priority = models.CharField('الأولوية', max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField('الحالة', max_length=16, choices=Status.choices, default=Status.NEW, db_index=True)
    # فارغ حين يُنشئه المساعد الآلي من واتساب (source='whatsapp')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name='service_requests_created', verbose_name='أنشأه')
    source = models.CharField('المصدر', max_length=10, choices=Source.choices, default=Source.STAFF)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='service_requests_assigned', verbose_name='المسؤول')
    due_at = models.DateTimeField('الموعد النهائي', null=True, blank=True, db_index=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    escalation_count = models.PositiveIntegerField(default=0)
    resolution_note = models.TextField('ملاحظة الحل', blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'طلب خدمة'
        verbose_name_plural = 'طلبات الخدمة'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'due_at']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['supplier', '-created_at']),
        ]

    def __str__(self):
        return self.reference or f'طلب #{self.pk}'

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL

    @property
    def is_overdue(self):
        return bool(self.due_at and self.status in self.OPEN and self.due_at < timezone.now())

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f'SR-{self.created_at:%Y}-{self.pk:05d}'
            super().save(update_fields=['reference'])


class ServiceRequestDocument(models.Model):
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='documents')
    label = models.CharField('نوع المستند', max_length=120, blank=True)
    file = models.FileField(upload_to=document_upload_path, storage=private_storage)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'مستند طلب'
        verbose_name_plural = 'مستندات الطلبات'

    def __str__(self):
        return self.original_name


class RequestStatusHistory(models.Model):
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='history')
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'سجل حالة طلب'
        verbose_name_plural = 'سجل حالات الطلبات'

    @property
    def from_label(self):
        return ServiceRequest.Status(self.from_status).label if self.from_status else ''

    @property
    def to_label(self):
        return ServiceRequest.Status(self.to_status).label


class Appointment(models.Model):

    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'مجدول'
        COMPLETED = 'completed', 'تم'
        CANCELLED = 'cancelled', 'ملغى'
        NO_SHOW = 'no_show', 'لم يحضر'

    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT, related_name='appointments',
                                 verbose_name='المورد')
    request = models.ForeignKey(ServiceRequest, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='appointments', verbose_name='الطلب')
    title = models.CharField('العنوان', max_length=200)
    scheduled_at = models.DateTimeField('الموعد', db_index=True)
    duration_minutes = models.PositiveIntegerField('المدة (دقيقة)', default=30)
    location = models.CharField('المكان', max_length=200, blank=True)
    notes = models.TextField('ملاحظات', blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='appointments', verbose_name='المسؤول')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_at']
        verbose_name = 'موعد'
        verbose_name_plural = 'المواعيد'

    def __str__(self):
        return f'{self.title} · {self.scheduled_at:%Y-%m-%d %H:%M}'
