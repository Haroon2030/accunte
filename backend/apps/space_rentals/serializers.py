"""
إيجارات المساحات - Serializers
"""
from rest_framework import serializers
from .models import SpaceRental


class SpaceRentalSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = SpaceRental
        fields = [
            'id', 'code', 'title', 'branch', 'branch_name',
            'supplier', 'supplier_name', 'rental_type', 'monthly_rent',
            'start_date', 'end_date', 'notes', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
