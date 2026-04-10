"""
الموردين - Suppliers Models
"""

from django.db import models


class Supplier(models.Model):
    """المورد"""
    name = models.CharField("اسم المورد", max_length=300)
    code = models.CharField("رقم المورد", max_length=50, unique=True)
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
