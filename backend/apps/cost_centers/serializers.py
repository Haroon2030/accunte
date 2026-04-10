"""
مراكز التكلفة - Serializers
"""
from rest_framework import serializers
from .models import CostCenter


class CostCenterSerializer(serializers.ModelSerializer):
    branches_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = CostCenter
        fields = [
            'id', 'name', 'code', 'description', 
            'is_active', 'branches_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class CostCenterListSerializer(serializers.ModelSerializer):
    """نسخة مختصرة للقوائم المنسدلة"""
    class Meta:
        model = CostCenter
        fields = ['id', 'name', 'code']
