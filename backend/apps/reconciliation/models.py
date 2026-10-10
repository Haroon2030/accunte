"""
حالات المطابقة المالية - Reconciliation Models
"""
import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .storage import private_storage


def document_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f'reconciliation/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}'


class ReconciliationCase(models.Model):
    """حالة مطابقة لمورد عن فترة مالية."""

    class Status(models.TextChoices):
        NEW = 'new', 'جديدة'
        PENDING_DOCS = 'pending_docs', 'بانتظار المستندات'
        READY_FOR_DISTRIBUTION = 'ready_for_distribution', 'جاهزة للتوزيع'
        ASSIGNED = 'assigned', 'مسندة'
        RECONCILING = 'reconciling', 'قيد المطابقة'
        WAITING_VENDOR = 'waiting_vendor', 'بانتظار المورد'
        DISCREPANCY_FOUND = 'discrepancy_found', 'تم رصد فروقات'
        PENDING_REVIEW = 'pending_review', 'بانتظار المراجعة'
        COMPLETED = 'completed', 'مكتملة'
        CLOSED = 'closed', 'مغلقة'
        CANCELLED = 'cancelled', 'ملغاة'

    class Priority(models.TextChoices):
        LOW = 'low', 'منخفضة'
        NORMAL = 'normal', 'عادية'
        HIGH = 'high', 'عالية'
        URGENT = 'urgent', 'عاجلة'

    TERMINAL = (Status.COMPLETED, Status.CLOSED, Status.CANCELLED)
    OPEN_STATUSES = (
        Status.ASSIGNED, Status.RECONCILING, Status.WAITING_VENDOR,
        Status.DISCREPANCY_FOUND, Status.PENDING_REVIEW,
    )

    reference = models.CharField('الرقم المرجعي', max_length=30, unique=True, null=True, blank=True, editable=False)
    supplier = models.ForeignKey(
        'suppliers.Supplier', on_delete=models.PROTECT, related_name='reconciliation_cases', verbose_name='المورد')
    branches = models.ManyToManyField('branches.Branch', related_name='reconciliation_cases',
                                      verbose_name='الفروع', blank=True)
    period_start = models.DateField('بداية الفترة')
    period_end = models.DateField('نهاية الفترة')
    status = models.CharField('الحالة', max_length=24, choices=Status.choices, default=Status.NEW, db_index=True)
    priority = models.CharField('الأولوية', max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    due_date = models.DateField('تاريخ الاستحقاق', null=True, blank=True)
    assigned_accountant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_reconciliations', verbose_name='المحاسب المسؤول')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_reconciliations',
        verbose_name='أنشأها')
    notes = models.TextField('ملاحظات', blank=True)
    created_at = models.DateTimeField('تاريخ الإنشاء', auto_now_add=True)
    updated_at = models.DateTimeField('آخر تحديث', auto_now=True)
    closed_at = models.DateTimeField('تاريخ الإغلاق', null=True, blank=True)

    class Meta:
        verbose_name = 'حالة مطابقة'
        verbose_name_plural = 'حالات المطابقة'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(check=Q(period_end__gte=F('period_start')), name='recon_period_valid'),
        ]
        indexes = [
            models.Index(fields=['assigned_accountant', 'status']),
            models.Index(fields=['status', 'due_date']),
            models.Index(fields=['supplier', '-created_at']),
        ]

    def __str__(self):
        return self.reference or f'مطابقة #{self.pk}'

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL

    @property
    def is_overdue(self):
        return bool(self.due_date and not self.is_terminal and self.due_date < timezone.localdate())

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:   # الرقم المرجعي من المفتاح الأساسي: فريد بلا سباق تزامن
            self.reference = f'RC-{self.created_at:%Y}-{self.pk:05d}'
            super().save(update_fields=['reference'])


class ReconciliationDocument(models.Model):
    """مستند مرفق بحالة المطابقة (كشف حساب المورد وغيره)."""

    class DocType(models.TextChoices):
        STATEMENT = 'statement', 'كشف حساب المورد'
        SUPPORTING = 'supporting', 'مستند داعم'
        OTHER = 'other', 'أخرى'

    case = models.ForeignKey(ReconciliationCase, on_delete=models.CASCADE, related_name='documents',
                             verbose_name='الحالة')
    doc_type = models.CharField('النوع', max_length=12, choices=DocType.choices, default=DocType.STATEMENT)
    file = models.FileField('الملف', upload_to=document_upload_path, storage=private_storage)
    original_name = models.CharField('اسم الملف الأصلي', max_length=255)
    size = models.PositiveIntegerField('الحجم (بايت)', default=0)
    sha256 = models.CharField('بصمة الملف', max_length=64, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    related_name='+', verbose_name='رفعه')
    uploaded_at = models.DateTimeField('تاريخ الرفع', auto_now_add=True)

    class Meta:
        verbose_name = 'مستند مطابقة'
        verbose_name_plural = 'مستندات المطابقة'
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.original_name


class ReconciliationResult(models.Model):
    """نتيجة المطابقة: الرصيدان والفرق والتوصية."""
    case = models.OneToOneField(ReconciliationCase, on_delete=models.CASCADE, related_name='result',
                                verbose_name='الحالة')
    supplier_balance = models.DecimalField('رصيد المورد', max_digits=16, decimal_places=2, default=Decimal('0'))
    company_balance = models.DecimalField('رصيد الشركة', max_digits=16, decimal_places=2, default=Decimal('0'))
    recommended_resolution = models.TextField('التوصية', blank=True)
    notes = models.TextField('ملاحظات', blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    related_name='+', verbose_name='سجّلها')
    updated_at = models.DateTimeField('آخر تحديث', auto_now=True)

    class Meta:
        verbose_name = 'نتيجة مطابقة'
        verbose_name_plural = 'نتائج المطابقة'

    @property
    def difference(self):
        return self.supplier_balance - self.company_balance

    def __str__(self):
        return f'نتيجة {self.case}'


class ReconciliationDifference(models.Model):
    """بند فرق: فاتورة أو دفعة متعارضة بين المورد والشركة."""

    class Kind(models.TextChoices):
        MISSING_INVOICE = 'missing_invoice', 'فاتورة غير مسجلة'
        MISSING_PAYMENT = 'missing_payment', 'دفعة غير مسجلة'
        AMOUNT_MISMATCH = 'amount_mismatch', 'اختلاف مبلغ'
        DUPLICATE = 'duplicate', 'قيد مكرر'
        OTHER = 'other', 'أخرى'

    case = models.ForeignKey(ReconciliationCase, on_delete=models.CASCADE, related_name='differences',
                             verbose_name='الحالة')
    kind = models.CharField('النوع', max_length=20, choices=Kind.choices, default=Kind.OTHER)
    document_ref = models.CharField('رقم الفاتورة/الدفعة', max_length=100, blank=True)
    document_date = models.DateField('التاريخ', null=True, blank=True)
    supplier_amount = models.DecimalField('مبلغ المورد', max_digits=16, decimal_places=2, default=Decimal('0'))
    company_amount = models.DecimalField('مبلغ الشركة', max_digits=16, decimal_places=2, default=Decimal('0'))
    description = models.TextField('الوصف', blank=True)
    recommended_resolution = models.TextField('الحل المقترح', blank=True)
    attachment = models.FileField('مرفق', upload_to=document_upload_path, storage=private_storage, blank=True)
    attachment_name = models.CharField(max_length=255, blank=True)
    is_resolved = models.BooleanField('تمت التسوية', default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name='+', verbose_name='سجّله')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'فرق مطابقة'
        verbose_name_plural = 'فروقات المطابقة'
        ordering = ['is_resolved', 'document_date', 'id']

    @property
    def difference(self):
        return self.supplier_amount - self.company_amount

    def __str__(self):
        return f'{self.get_kind_display()} · {self.document_ref}'


class WorkAssignment(models.Model):
    """سجل الإسنادات: من أُسندت إليه الحالة ومتى ومن أسندها."""
    case = models.ForeignKey(ReconciliationCase, on_delete=models.CASCADE, related_name='assignments',
                             verbose_name='الحالة')
    accountant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='work_assignments', verbose_name='المحاسب')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    related_name='+', verbose_name='أسندها')
    is_active = models.BooleanField('نشط', default=True)
    note = models.CharField('ملاحظة', max_length=300, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'إسناد'
        verbose_name_plural = 'الإسنادات'
        ordering = ['-assigned_at']
        constraints = [
            models.UniqueConstraint(fields=['case'], condition=Q(is_active=True), name='one_active_assignment'),
        ]

    def __str__(self):
        return f'{self.case} → {self.accountant}'


class StatusHistory(models.Model):
    """سجل تغيّر حالات المطابقة (يُكتب ولا يُعدَّل)."""
    case = models.ForeignKey(ReconciliationCase, on_delete=models.CASCADE, related_name='history',
                             verbose_name='الحالة')
    from_status = models.CharField('من', max_length=24, blank=True)
    to_status = models.CharField('إلى', max_length=24)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name='+', verbose_name='بواسطة')
    reason = models.TextField('السبب', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'سجل حالة'
        verbose_name_plural = 'سجل الحالات'
        ordering = ['created_at', 'id']

    @property
    def from_label(self):
        return ReconciliationCase.Status(self.from_status).label if self.from_status else ''

    @property
    def to_label(self):
        return ReconciliationCase.Status(self.to_status).label

    def __str__(self):
        return f'{self.case}: {self.from_status} → {self.to_status}'
