"""
طلبات الدفع - Payments Models
نظام إدارة سير عمل طلبات الدفع
"""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class PaymentRequest(models.Model):
    """طلب الدفع - النموذج الرئيسي"""
    
    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        PROPOSED = "proposed", "مقترح"
        FIRST_APPROVED = "first_approved", "موافقة مبدئية"
        AUDITED = "audited", "تمت المراجعة"
        FINAL_APPROVED = "final_approved", "اعتماد نهائي"
        REJECTED = "rejected", "مرفوض"

    # العلاقات الأساسية
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        verbose_name="الفرع",
        related_name="payment_requests",
    )
    bank = models.ForeignKey(
        'banks.Bank',
        on_delete=models.SET_NULL,
        verbose_name="البنك",
        related_name="payment_requests",
        null=True,
        blank=True,
    )

    # المبالغ المالية
    amount = models.DecimalField(
        "المبلغ الإجمالي",
        max_digits=14,
        decimal_places=2,
        default=0
    )
    current_balance = models.DecimalField(
        "الرصيد الحالي",
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # حقول الحساب
    analytical_account = models.CharField("الحساب التحليلي", max_length=50, blank=True)
    supplier_account = models.CharField("حساب المورد", max_length=50, default="21101001")
    cost_center = models.CharField("مركز التكلفة", max_length=50, blank=True)
    bank_account_number = models.CharField("رقم الحساب البنكي", max_length=50, blank=True)
    bank_code = models.CharField("رمز البنك", max_length=50, blank=True)

    # الحالة والملاحظات
    status = models.CharField(
        "الحالة",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    notes = models.TextField("ملاحظات", blank=True)
    rejection_reason = models.TextField("سبب الرفض", blank=True)

    # المستخدمون المسؤولون عن كل مرحلة
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name="أنشأه",
        related_name="created_payments",
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name="اقترحه",
        related_name="proposed_payments",
        null=True,
        blank=True,
    )
    first_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name="موافق مبدئي",
        related_name="first_approved_payments",
        null=True,
        blank=True,
    )
    audited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name="المدقق",
        related_name="audited_payments",
        null=True,
        blank=True,
    )
    final_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name="الموافق النهائي",
        related_name="final_approved_payments",
        null=True,
        blank=True,
    )

    # التواريخ
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)
    proposed_at = models.DateTimeField("تاريخ الاقتراح", null=True, blank=True)
    first_approved_at = models.DateTimeField("تاريخ الموافقة المبدئية", null=True, blank=True)
    audited_at = models.DateTimeField("تاريخ التدقيق", null=True, blank=True)
    final_approved_at = models.DateTimeField("تاريخ الاعتماد النهائي", null=True, blank=True)

    class Meta:
        verbose_name = "طلب دفع"
        verbose_name_plural = "طلبات الدفع"
        ordering = ["-created_at"]
        permissions = [
            ("can_propose", "يمكنه اقتراح الدفعة"),
            ("can_first_approve", "يمكنه الموافقة المبدئية"),
            ("can_audit", "يمكنه التدقيق المالي"),
            ("can_final_approve", "يمكنه الاعتماد النهائي"),
            ("can_reject", "يمكنه الرفض"),
        ]

    def __str__(self):
        return f"طلب #{self.pk} - {self.branch.name}"

    @property
    def status_display(self):
        return self.get_status_display()

    @property
    def items_count(self):
        return self.items.count()

    @property
    def total_amount(self):
        return self.items.aggregate(total=models.Sum('amount'))['total'] or 0

    def get_available_transitions(self, user):
        """الحصول على الانتقالات المتاحة للمستخدم"""
        transitions = []
        
        if self.status == self.Status.DRAFT:
            if user.has_perm('payments.can_propose'):
                transitions.append({'status': 'proposed', 'label': 'تقديم للاعتماد', 'color': 'blue'})
        
        elif self.status == self.Status.PROPOSED:
            if user.has_perm('payments.can_first_approve'):
                transitions.append({'status': 'first_approved', 'label': 'موافقة مبدئية', 'color': 'yellow'})
            if user.has_perm('payments.can_reject'):
                transitions.append({'status': 'rejected', 'label': 'رفض', 'color': 'red'})
        
        elif self.status == self.Status.FIRST_APPROVED:
            if user.has_perm('payments.can_audit'):
                transitions.append({'status': 'audited', 'label': 'تدقيق', 'color': 'purple'})
            if user.has_perm('payments.can_reject'):
                transitions.append({'status': 'rejected', 'label': 'رفض', 'color': 'red'})
        
        elif self.status == self.Status.AUDITED:
            if user.has_perm('payments.can_final_approve'):
                transitions.append({'status': 'final_approved', 'label': 'اعتماد نهائي', 'color': 'green'})
            if user.has_perm('payments.can_reject'):
                transitions.append({'status': 'rejected', 'label': 'رفض', 'color': 'red'})
        
        return transitions


class PaymentRequestItem(models.Model):
    """بند طلب الدفع - تفاصيل كل مورد في الطلب"""
    
    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "جاري المعالجة"
        APPROVED = "approved", "معتمد"
        REJECTED = "rejected", "مرفوض"

    payment_request = models.ForeignKey(
        PaymentRequest,
        on_delete=models.CASCADE,
        verbose_name="طلب الدفع",
        related_name="items",
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        verbose_name="المورد",
        related_name="payment_items",
    )
    supplier_code = models.CharField("كود المورد", max_length=50, blank=True)

    # المبالغ
    current_balance = models.DecimalField(
        "الرصيد الحالي",
        max_digits=14,
        decimal_places=2,
        default=0
    )
    amount = models.DecimalField(
        "الدفعة المقترحة",
        max_digits=14,
        decimal_places=2,
        default=0
    )
    proposed_amount = models.DecimalField(
        "مقترح المشتريات",
        max_digits=14,
        decimal_places=2,
        default=0
    )
    abu_alaa_proposed = models.DecimalField(
        "اقتراح أبو علاء",
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # حالات الموافقة
    sultan_approval = models.CharField(
        "موافقة سلطان",
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    auditor_status = models.CharField(
        "حالة المدقق",
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    abu_alaa_final = models.CharField(
        "اعتماد أبو علاء النهائي",
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )
    cfo_approval = models.CharField(
        "موافقة المدير المالي",
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )

    # بيانات إضافية
    invoice_number = models.CharField("رقم الفاتورة", max_length=100, blank=True)
    invoice_date = models.DateField("تاريخ الفاتورة", null=True, blank=True)
    description = models.TextField("الوصف", blank=True)
    notes = models.TextField("ملاحظات", blank=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    class Meta:
        verbose_name = "بند الدفع"
        verbose_name_plural = "بنود الدفع"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.supplier.name} - {self.amount}"

    def save(self, *args, **kwargs):
        # تعبئة كود المورد تلقائياً
        if not self.supplier_code and self.supplier:
            self.supplier_code = self.supplier.code
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """سجل المراجعة - تتبع التغييرات"""
    
    payment_request = models.ForeignKey(
        PaymentRequest,
        on_delete=models.CASCADE,
        verbose_name="طلب الدفع",
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name="المستخدم",
        related_name="audit_logs",
    )
    action = models.CharField("الإجراء", max_length=500)
    old_status = models.CharField("الحالة السابقة", max_length=20, blank=True)
    new_status = models.CharField("الحالة الجديدة", max_length=20, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    ip_address = models.GenericIPAddressField("عنوان IP", null=True, blank=True)
    user_agent = models.TextField("المتصفح", blank=True)
    created_at = models.DateTimeField("التاريخ", auto_now_add=True)

    class Meta:
        verbose_name = "سجل مراجعة"
        verbose_name_plural = "سجل المراجعة"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.created_at}"
