from django.contrib import admin
from .models import Item, ItemBatch


class ItemInline(admin.TabularInline):
    model = Item
    extra = 0


@admin.register(ItemBatch)
class ItemBatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'supplier', 'payment_status', 'created_at', 'created_by']
    list_filter = ['payment_status', 'supplier', 'created_at']
    search_fields = ['supplier__name']
    inlines = [ItemInline]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['barcode', 'name', 'batch', 'package', 'amount', 'is_active']
    list_filter = ['is_active', 'batch__supplier']
    search_fields = ['barcode', 'name', 'batch__supplier__name']
