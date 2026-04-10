"""
الفروع - Serializers
"""
from rest_framework import serializers
from .models import Branch
from apps.cost_centers.serializers import CostCenterListSerializer


class BranchSerializer(serializers.ModelSerializer):
    cost_center_name = serializers.CharField(source='cost_center.name', read_only=True)
    banks_count = serializers.IntegerField(read_only=True)
    payments_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'code', 'cost_center', 'cost_center_name',
            'address', 'phone', 'is_active',
            'banks_count', 'payments_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class BranchListSerializer(serializers.ModelSerializer):
    """نسخة مختصرة للقوائم المنسدلة"""
    class Meta:
        model = Branch
        fields = ['id', 'name', 'code']


class BranchDetailSerializer(serializers.ModelSerializer):
    cost_center = CostCenterListSerializer(read_only=True)
    banks_count = serializers.IntegerField(read_only=True)
    payments_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'code', 'cost_center',
            'address', 'phone', 'is_active',
            'banks_count', 'payments_count',
            'created_at', 'updated_at'
        ]
