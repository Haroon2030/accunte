"""
مقترحات الدفع - Payment Proposals
فصل صارم بين: حالة المطابقة ← مقترح الدفع ← تنفيذ الدفع الفعلي.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.reconciliation.models import document_upload_path
from apps.reconciliation.storage import private_storage


class PaymentProposal(models.Model):

    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        SUBMITTED = 'submitted', 'مقدَّم'
        PENDING_REVIEW = 'pending_review', 'قيد المراجعة'
        NEEDS_INFO = 'needs_info', 'مطلوب استيضاح'
        APPROVED = 'approved', 'معتمد'
        REJECTED = 'rejected', 'مرفوض'
        DISPATCHED = 'dispatched', 'تم الصرف'
        CONFIRMED_PAID = 'confirmed_paid', 'تأكد السداد'
        CANCELLED = 'cancelled', 'ملغي'

    TERMINAL = (Status.REJECTED, Status.CONFIRMED_PAID, Status.CANCELLED)
    # الحالات التي تُحسب "نشطة": تمنع مقترحًا ثانيًا لنفس المطابقة
    INACTIVE = (Status.REJECTED, Status.CANCELLED)

    reference = models.CharField('الرقم المرجعي', max_length=30, unique=True, null=True, blank=True, editable=False)
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT, related_name='payment_proposals',
                                 verbose_name='المورد')
    branch = models.ForeignKey('branches.Branch', on_delete=models.PROTECT, related_name='payment_proposals',
                               verbose_name='الفرع')
    reconciliation_case = models.ForeignKey(
        'reconciliation.ReconciliationCase', on_delete=models.PROTECT, related_name='payment_proposals',
        verbose_name='حالة المطابقة')
    total_dues = models.DecimalField('إجمالي المستحقات', max_digits=16, decimal_places=2)
    proposed_amount = models.DecimalField('المبلغ المقترح', max_digits=16, decimal_places=2)
    currency = models.CharField('العملة', max_length=3, default='SAR')
    justification = models.TextField('المبررات')
    status = models.CharField('الحالة', max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    requires_cfo = models.BooleanField('يتطلب اعتماد المدير المالي', default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='created_proposals', verbose_name='أنشأه')
    created_at = models.DateTimeField('تاريخ الإنشاء', auto_now_add=True)
    updated_at = models.DateTimeField('آخر تحديث', auto_now=True)
    submitted_at = models.DateTimeField('تاريخ التقديم', null=True, blank=True)
    decided_at = models.DateTimeField('تاريخ القرار', null=True, blank=True)

    class Meta:
        verbose_name = 'مقترح دفع'
        verbose_name_plural = 'مقترحات الدفع'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(check=Q(proposed_amount__gt=0), name='proposal_amount_positive'),
            models.CheckConstraint(check=Q(proposed_amount__lte=F('total_dues')), name='proposal_not_above_dues'),
            # مقترح نشط واحد فقط لكل حالة مطابقة: يمنع العدّ المزدوج في التقارير
            models.UniqueConstraint(
                fields=['reconciliation_case'], name='one_active_proposal_per_case',
                condition=~Q(status__in=['rejected', 'cancelled'])),
        ]
        indexes = [models.Index(fields=['status', '-created_at']), models.Index(fields=['supplier', 'status'])]

    def __str__(self):
        return self.reference or f'مقترح #{self.pk}'

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            self.reference = f'PP-{self.created_at:%Y}-{self.pk:05d}'
            super().save(update_fields=['reference'])


class ProposalAttachment(models.Model):
    proposal = models.ForeignKey(PaymentProposal, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to=document_upload_path, storage=private_storage)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'مرفق مقترح'
        verbose_name_plural = 'مرفقات المقترحات'

    def __str__(self):
        return self.original_name


class PaymentApproval(models.Model):
    """قرار مراجعة واحد. المقترح قد يملك عدة قرارات (استيضاح ثم اعتماد مثلًا)."""

    class Decision(models.TextChoices):
        APPROVED = 'approved', 'اعتماد'
        REJECTED = 'rejected', 'رفض'
        NEEDS_INFO = 'needs_info', 'طلب استيضاح'

    proposal = models.ForeignKey(PaymentProposal, on_delete=models.CASCADE, related_name='approvals')
    decision = models.CharField('القرار', max_length=12, choices=Decision.choices)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                   verbose_name='اتخذه')
    amount_at_decision = models.DecimalField('المبلغ وقت القرار', max_digits=16, decimal_places=2)
    notes = models.TextField('ملاحظات المعتمِد', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name = 'قرار اعتماد'
        verbose_name_plural = 'قرارات الاعتماد'

    def __str__(self):
        return f'{self.proposal} · {self.get_decision_display()}'


class PaymentExecutionRecord(models.Model):
    """تنفيذ الصرف الفعلي. منفصل عن المقترح ويتطلب مستخدمَين مختلفين للصرف والتأكيد."""
    proposal = models.OneToOneField(PaymentProposal, on_delete=models.PROTECT, related_name='execution')
    executed_amount = models.DecimalField('المبلغ المصروف', max_digits=16, decimal_places=2)
    bank_reference = models.CharField('مرجع التحويل البنكي', max_length=100)
    payment_date = models.DateField('تاريخ الصرف')
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                      verbose_name='نفّذه')
    dispatched_at = models.DateTimeField(auto_now_add=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', verbose_name='أكّده')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField('ملاحظات', blank=True)

    class Meta:
        verbose_name = 'سجل تنفيذ دفع'
        verbose_name_plural = 'سجلات تنفيذ الدفع'
        constraints = [
            models.CheckConstraint(check=Q(executed_amount__gt=Decimal('0')), name='execution_amount_positive'),
        ]

    def __str__(self):
        return f'{self.proposal} · {self.bank_reference}'
