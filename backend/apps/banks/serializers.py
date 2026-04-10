"""
البنوك - Serializers
"""
from rest_framework import serializers
from .models import Bank


class BankSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    account_type_display = serializers.CharField(read_only=True)
    currency_display = serializers.CharField(read_only=True)
    
    class Meta:
        model = Bank
        fields = [
            'id', 'name', 'code', 'account_number',
            'iban', 'swift_code', 'analytical_number',
            'account_type', 'account_type_display',
            'currency', 'currency_display', 'balance',
            'branch', 'branch_name', 'branch_code', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class BankListSerializer(serializers.ModelSerializer):
    """نسخة مختصرة للقوائم المنسدلة"""
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    
    class Meta:
        model = Bank
        fields = ['id', 'name', 'code', 'branch_name', 'balance', 'is_active']
