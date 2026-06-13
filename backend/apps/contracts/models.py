"""
العقود - Contracts Models
"""

from django.db import models


class Contract(models.Model):
    """عقد مع مورد"""

    class ContractType(models.TextChoices):
        FIXED_DISCOUNT = 'fixed_discount', 'خصم ثابت'
        MONTHLY_INCENTIVE = 'monthly_incentive', 'حافز شهري'
        ANNUAL_INCENTIVE = 'annual_incentive', 'حافز سنوي'

    title = models.CharField("عنوان العقد", max_length=300)
    code = models.CharField("رقم العقد", max_length=50, unique=True)
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        verbose_name="المورد",
        related_name="contracts",
    )
    contract_type = models.CharField(
        "نوع العقد",
        max_length=20,
        choices=ContractType.choices,
    )
    value = models.DecimalField(
        "القيمة",
        max_digits=12,
        decimal_places=2,
        help_text="نسبة مئوية للخصم الثابت، أو مبلغ للحافز الشهري/السنوي",
    )
    start_date = models.DateField("تاريخ البداية")
    end_date = models.DateField("تاريخ النهاية", null=True, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    class Meta:
        verbose_name = "عقد"
        verbose_name_plural = "العقود"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} - {self.title}"

    @property
    def contract_type_display(self):
        return self.get_contract_type_display()

    @property
    def value_display(self):
        if self.contract_type == self.ContractType.FIXED_DISCOUNT:
            return f"{self.value}%"
        return f"{self.value} ر.س"
