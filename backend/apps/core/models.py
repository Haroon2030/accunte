"""
النظام الأساسي - Core Models
"""

from django.db import models
from django.conf import settings


class Permission(models.Model):
    """صلاحية في النظام"""
    code = models.CharField("رمز الصلاحية", max_length=100, unique=True)
    name = models.CharField("اسم الصلاحية", max_length=200)
    description = models.TextField("الوصف", blank=True)
    module = models.CharField("الوحدة", max_length=100, choices=[
        ('banks', 'البنوك'),
        ('branches', 'الفروع'),
        ('suppliers', 'الموردين'),
        ('cost_centers', 'مراكز التكلفة'),
        ('payments', 'المدفوعات'),
        ('users', 'المستخدمين'),
        ('reports', 'التقارير'),
        ('settings', 'الإعدادات'),
    ])
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    
    class Meta:
        verbose_name = "صلاحية"
        verbose_name_plural = "الصلاحيات"
        ordering = ['module', 'name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Role(models.Model):
    """دور المستخدم"""
    
    class RoleType(models.TextChoices):
        ADMIN = 'admin', 'مدير النظام'
        MANAGER = 'manager', 'مدير'
        AUDITOR = 'auditor', 'مدقق'
        BRANCH_EMPLOYEE = 'branch_employee', 'موظف فرع'
    
    name = models.CharField("اسم الدور", max_length=100, unique=True)
    role_type = models.CharField(
        "نوع الدور",
        max_length=20,
        choices=RoleType.choices,
        default=RoleType.BRANCH_EMPLOYEE
    )
    description = models.TextField("الوصف", blank=True)
    permissions = models.ManyToManyField(
        Permission,
        verbose_name="الصلاحيات",
        related_name="roles",
        blank=True
    )
    is_system_role = models.BooleanField("دور نظام", default=False, help_text="الأدوار الأساسية لا يمكن حذفها")
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("تاريخ التحديث", auto_now=True)
    
    class Meta:
        verbose_name = "دور"
        verbose_name_plural = "الأدوار"
        ordering = ['name']

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # منع حذف أو تعديل دور الأدمن
        if self.pk and self.role_type == self.RoleType.ADMIN and self.is_system_role:
            old_instance = Role.objects.filter(pk=self.pk).first()
            if old_instance and old_instance.role_type == self.RoleType.ADMIN:
                # لا تغير نوع الدور للأدمن
                self.role_type = self.RoleType.ADMIN
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        # منع حذف أدوار النظام
        if self.is_system_role:
            raise ValueError("لا يمكن حذف أدوار النظام")
        super().delete(*args, **kwargs)


class UserProfile(models.Model):
    """ملف المستخدم الموسع"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="المستخدم",
        related_name="profile",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        verbose_name="الدور",
        related_name="users",
        null=True,
        blank=True
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.SET_NULL,
        verbose_name="الفرع",
        related_name="employees",
        null=True,
        blank=True,
        help_text="الفرع الذي ينتمي إليه الموظف (مطلوب لموظفي الفروع)"
    )
    phone = models.CharField("رقم الهاتف", max_length=20, blank=True)
    department = models.CharField("القسم", max_length=100, blank=True)
    position = models.CharField("المنصب", max_length=100, blank=True)
    avatar = models.ImageField("الصورة الشخصية", upload_to="avatars/", blank=True)
    is_protected = models.BooleanField("محمي", default=False, help_text="المستخدمين المحميين لا يمكن حذفهم أو تعديلهم")
    
    class Meta:
        verbose_name = "ملف مستخدم"
        verbose_name_plural = "ملفات المستخدمين"

    def __str__(self):
        return f"ملف {self.user.username}"
    
    def get_permissions(self):
        """الحصول على جميع صلاحيات المستخدم"""
        if self.role:
            return list(self.role.permissions.filter(is_active=True).values_list('code', flat=True))
        return []
    
    @property
    def role_type(self):
        """الحصول على نوع الدور"""
        if self.role:
            return self.role.role_type
        return None
    
    @property
    def is_admin(self):
        """هل المستخدم مدير نظام؟"""
        return self.role and self.role.role_type == Role.RoleType.ADMIN
    
    @property
    def is_manager(self):
        """هل المستخدم مدير؟"""
        return self.role and self.role.role_type == Role.RoleType.MANAGER
    
    @property
    def is_auditor(self):
        """هل المستخدم مدقق؟"""
        return self.role and self.role.role_type == Role.RoleType.AUDITOR
    
    @property
    def is_branch_employee(self):
        """هل المستخدم موظف فرع؟"""
        return self.role and self.role.role_type == Role.RoleType.BRANCH_EMPLOYEE
    
    def can_see_all_branches(self):
        """هل يمكن للمستخدم رؤية جميع الفروع؟"""
        if not self.role:
            return False
        return self.role.role_type in [Role.RoleType.ADMIN, Role.RoleType.MANAGER, Role.RoleType.AUDITOR]
    
    def can_edit_auditor_status(self):
        """هل يمكن للمستخدم تغيير حالة المدقق؟"""
        if not self.role:
            return False
        return self.role.role_type in [Role.RoleType.ADMIN, Role.RoleType.AUDITOR]


class SystemSettings(models.Model):
    """إعدادات النظام"""
    key = models.CharField("المفتاح", max_length=100, unique=True)
    value = models.TextField("القيمة")
    description = models.TextField("الوصف", blank=True)
    
    class Meta:
        verbose_name = "إعداد نظام"
        verbose_name_plural = "إعدادات النظام"

    def __str__(self):
        return self.key
