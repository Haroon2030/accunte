"""
البنوك - Banks Models
"""

from django.db import models


class Bank(models.Model):
    """البنك"""
    ACCOUNT_TYPE_CHOICES = [
        ('current', 'جاري'),
        ('savings', 'توفير'),
        ('investment', 'استثماري'),
    ]
    
    CURRENCY_CHOICES = [
        ('SAR', 'ريال سعودي'),
        ('USD', 'دولار أمريكي'),
        ('EUR', 'يورو'),
    ]
    
    name = models.CharField("اسم البنك", max_length=200)
    code = models.CharField("رمز البنك", max_length=20, unique=True)
    account_number = models.CharField("رقم الحساب", max_length=50, blank=True)
    iban = models.CharField("رقم IBAN", max_length=50, blank=True)
    swift_code = models.CharField("رمز SWIFT", max_length=20, blank=True)
    analytical_number = models.CharField("الرقم التحليلي", max_length=50, blank=True)
    account_type = models.CharField(
        "نوع الحساب",
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default='current'
    )
    currency = models.CharField(
        "العملة",
        max_length=10,
        choices=CURRENCY_CHOICES,
        default='SAR'
    )
    balance = models.DecimalField(
        "الرصيد",
        max_digits=18,
        decimal_places=2,
        default=0
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.SET_NULL,
        verbose_name="الفرع",
        related_name="bank_accounts",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)

    class Meta:
        verbose_name = "بنك"
        verbose_name_plural = "البنوك"
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"
    
    @property
    def account_type_display(self):
        return dict(self.ACCOUNT_TYPE_CHOICES).get(self.account_type, self.account_type)
    
    @property
    def currency_display(self):
        return dict(self.CURRENCY_CHOICES).get(self.currency, self.currency)
