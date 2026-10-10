"""
الموردين - Suppliers Models
"""

from django.conf import settings
from django.db import models


class Supplier(models.Model):
    """المورد"""
    name = models.CharField("اسم المورد", max_length=300)
    code = models.CharField("رقم المورد", max_length=50, unique=True)
    financial_system_id = models.CharField(
        "رقم المورد في النظام المالي", max_length=50, null=True, blank=True)
    contact_person = models.CharField("الشخص المسؤول", max_length=150, blank=True)
    branches = models.ManyToManyField(
        'branches.Branch', verbose_name="الفروع المرتبطة", related_name="suppliers", blank=True)
    assigned_accountant = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="المحاسب المسؤول",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_suppliers")
    engagement_history = models.TextField("سجل التعامل", blank=True)
    phone = models.CharField("الهاتف", max_length=20, blank=True)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    address = models.TextField("العنوان", blank=True)
    tax_number = models.CharField("الرقم الضريبي", max_length=50, blank=True)
    commercial_register = models.CharField("السجل التجاري", max_length=50, blank=True)
    bank_name = models.CharField("اسم البنك", max_length=100, blank=True)
    bank_account = models.CharField("رقم الحساب البنكي", max_length=50, blank=True)
    iban = models.CharField("رقم الآيبان", max_length=50, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    class Meta:
        verbose_name = "مورد"
        verbose_name_plural = "الموردين"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["financial_system_id"], name="uniq_supplier_financial_id",
                condition=models.Q(financial_system_id__isnull=False) & ~models.Q(financial_system_id=""),
            ),
            models.UniqueConstraint(
                fields=["tax_number"], name="uniq_supplier_tax_number",
                condition=~models.Q(tax_number=""),
            ),
        ]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_active", "name"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def total_payments(self):
        """إجمالي المدفوعات للمورد"""
        from apps.payments.models import PaymentRequestItem
        return PaymentRequestItem.objects.filter(
            supplier=self,
            payment_request__status='final_approved'
        ).aggregate(total=models.Sum('amount'))['total'] or 0


class SupplierContact(models.Model):
    """جهة اتصال للمورد. رقم الهاتف ليس هو معرّف المورد، فالمورد قد يملك عدة جهات."""
    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="contacts", verbose_name="المورد")
    name = models.CharField("الاسم", max_length=150, blank=True)
    job_title = models.CharField("المسمى", max_length=100, blank=True)
    phone = models.CharField("رقم الهاتف (دولي)", max_length=20, db_index=True)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    is_primary = models.BooleanField("رئيسي", default=False)
    is_approved = models.BooleanField("معتمد للتواصل", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)

    class Meta:
        verbose_name = "جهة اتصال مورد"
        verbose_name_plural = "جهات اتصال الموردين"
        ordering = ["-is_primary", "name"]
        constraints = [
            models.UniqueConstraint(fields=["supplier", "phone"], name="uniq_contact_supplier_phone"),
        ]

    def __str__(self):
        return f"{self.name or self.phone} ({self.supplier.code})"


class SupplierImportJob(models.Model):
    """مرحلة تجهيز (staging) لاستيراد Excel: تُحلَّل الصفوف وتُراجَع قبل الكتابة النهائية."""

    class Status(models.TextChoices):
        STAGED = "staged", "بانتظار التأكيد"
        COMMITTED = "committed", "تم الاستيراد"
        CANCELLED = "cancelled", "ملغي"

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="supplier_imports")
    filename = models.CharField("اسم الملف", max_length=255)
    status = models.CharField("الحالة", max_length=12, choices=Status.choices, default=Status.STAGED)
    rows = models.JSONField("الصفوف", default=list)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "عملية استيراد موردين"
        verbose_name_plural = "عمليات استيراد الموردين"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.filename} ({self.get_status_display()})"
