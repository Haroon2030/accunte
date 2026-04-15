"""
مراكز التكلفة - Cost Centers Models
"""

from django.db import models


class CostCenter(models.Model):
    """مركز التكلفة"""
    name = models.CharField("اسم مركز التكلفة", max_length=200)
    code = models.CharField("رمز مركز التكلفة", max_length=20, unique=True)
    description = models.TextField("الوصف", blank=True)
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    class Meta:
        verbose_name = "مركز تكلفة"
        verbose_name_plural = "مراكز التكلفة"
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"
