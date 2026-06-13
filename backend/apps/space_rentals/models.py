"""
إيجارات المساحات - Space Rentals Models
"""

from django.db import models


class SpaceRental(models.Model):
    """إيجار مساحة"""

    class RentalType(models.TextChoices):
        SHELF = 'shelf', 'إيجار رف'
        FLOOR_GONDOLA = 'floor_gondola', 'إيجار جندولة أرضية'

    code = models.CharField("رقم العقد", max_length=50, unique=True)
    title = models.CharField("اسم المساحة", max_length=300)
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        verbose_name="الفرع",
        related_name="space_rentals",
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        verbose_name="المورد",
        related_name="space_rentals",
    )
    rental_type = models.CharField(
        "نوع الإيجار",
        max_length=20,
        choices=RentalType.choices,
        default=RentalType.SHELF,
    )
    monthly_rent = models.DecimalField("الإيجار الشهري", max_digits=12, decimal_places=2)
    start_date = models.DateField("تاريخ البداية")
    end_date = models.DateField("تاريخ النهاية", null=True, blank=True)
    notes = models.TextField("ملاحظات", blank=True)
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    class Meta:
        verbose_name = "إيجار مساحة"
        verbose_name_plural = "إيجارات المساحات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} - {self.title}"
