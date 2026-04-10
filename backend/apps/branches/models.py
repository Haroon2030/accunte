"""
الفروع - Branches Models
"""

from django.db import models


class Branch(models.Model):
    """الفرع"""
    name = models.CharField("اسم الفرع", max_length=200)
    code = models.CharField("رمز الفرع", max_length=20, unique=True)
    cost_center = models.ForeignKey(
        'cost_centers.CostCenter',
        on_delete=models.SET_NULL,
        verbose_name="مركز التكلفة",
        related_name="branches",
        null=True,
        blank=True,
    )
    address = models.TextField("العنوان", blank=True)
    phone = models.CharField("الهاتف", max_length=20, blank=True)
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    class Meta:
        verbose_name = "فرع"
        verbose_name_plural = "الفروع"
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"
