"""
العقود - Serializers
"""
from rest_framework import serializers
from .models import Contract


class ContractSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    contract_type_display = serializers.CharField(source='get_contract_type_display', read_only=True)
    value_display = serializers.CharField(read_only=True)

    class Meta:
        model = Contract
        fields = [
            'id', 'title', 'code', 'supplier', 'supplier_name',
            'contract_type', 'contract_type_display', 'value', 'value_display',
            'start_date', 'end_date', 'notes', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
