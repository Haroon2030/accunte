"""
الأصناف - Items Models
"""

from django.conf import settings
from django.db import models


class ItemBatch(models.Model):
    """ملف أصناف - مجموعة أصناف محفوظة معاً"""

    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        verbose_name="الشركة / المورد",
        related_name="item_batches",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name="أنشئ بواسطة",
        related_name="item_batches",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)

    class Meta:
        verbose_name = "ملف أصناف"
        verbose_name_plural = "ملفات الأصناف"
        ordering = ["-created_at"]

    def __str__(self):
        return f"ملف #{self.pk} - {self.supplier.name}"


class Item(models.Model):
    """صنف ضمن ملف"""

    batch = models.ForeignKey(
        ItemBatch,
        on_delete=models.CASCADE,
        verbose_name="الملف",
        related_name="items",
    )
    barcode = models.CharField("باركود الصنف", max_length=100, unique=True)
    name = models.CharField("اسم الصنف", max_length=300)
    package = models.CharField("العبوة", max_length=100, help_text="مثل: علبة، كرتون، 500 مل")
    amount = models.DecimalField("المبلغ", max_digits=12, decimal_places=2)
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    class Meta:
        verbose_name = "صنف"
        verbose_name_plural = "الأصناف"
        ordering = ["name"]

    def __str__(self):
        return f"{self.barcode} - {self.name}"

    @property
    def supplier(self):
        return self.batch.supplier
