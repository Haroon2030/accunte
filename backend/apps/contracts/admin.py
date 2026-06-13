from django.contrib import admin
from .models import Contract


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['code', 'title', 'supplier', 'contract_type', 'value', 'is_active', 'start_date']
    list_filter = ['contract_type', 'is_active']
    search_fields = ['title', 'code', 'supplier__name']
