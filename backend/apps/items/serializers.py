"""
الأصناف - Serializers
"""
from rest_framework import serializers
from .models import Item, ItemBatch


class ItemSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='batch.supplier.name', read_only=True)

    class Meta:
        model = Item
        fields = [
            'id', 'batch', 'supplier_name', 'barcode', 'name',
            'package', 'amount', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class ItemBatchSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    items = ItemSerializer(many=True, read_only=True)

    class Meta:
        model = ItemBatch
        fields = [
            'id', 'supplier', 'supplier_name', 'payment_status', 'items_count', 'total_amount',
            'items', 'created_by', 'created_at',
        ]
        read_only_fields = ['created_by', 'created_at']
