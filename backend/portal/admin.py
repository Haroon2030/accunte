from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Attachment, Complaint, MatchRequest, Message, Supplier, User


@admin.register(User)
class PortalUserAdmin(UserAdmin):
    list_display = ('username', 'name', 'role', 'org', 'code', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'name', 'org', 'code', 'tax_no')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('البيانات', {'fields': ('name', 'role', 'org', 'code', 'tax_no', 'must_change_password')}),
        ('الصلاحيات', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('username', 'name', 'role', 'password1', 'password2')}),)


admin.site.register([MatchRequest, Complaint, Message, Attachment, Supplier])
