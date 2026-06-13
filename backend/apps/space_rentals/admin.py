from django.contrib import admin
from .models import SpaceRental


@admin.register(SpaceRental)
class SpaceRentalAdmin(admin.ModelAdmin):
    list_display = ['code', 'title', 'branch', 'supplier', 'monthly_rent', 'is_active']
    list_filter = ['is_active', 'branch', 'supplier']
    search_fields = ['code', 'title', 'supplier__name']
