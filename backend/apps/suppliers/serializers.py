"""
الموردين - Serializers
"""
from rest_framework import serializers
from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'code', 'phone', 'email', 'address',
            'tax_number', 'commercial_register',
            'bank_name', 'bank_account', 'iban',
            'notes', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class SupplierListSerializer(serializers.ModelSerializer):
    """نسخة مختصرة للقوائم المنسدلة"""
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'code']


class SupplierDetailSerializer(serializers.ModelSerializer):
    total_payments = serializers.SerializerMethodField()
    payments_count = serializers.SerializerMethodField()
    recent_payments = serializers.SerializerMethodField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'code', 'phone', 'email', 'address',
            'tax_number', 'commercial_register',
            'bank_name', 'bank_account', 'iban',
            'notes', 'is_active',
            'total_payments', 'payments_count', 'recent_payments',
            'created_at', 'updated_at'
        ]
    
    def get_total_payments(self, obj):
        return obj.total_payments
    
    def get_payments_count(self, obj):
        from apps.payments.models import PaymentRequestItem
        return PaymentRequestItem.objects.filter(supplier=obj).count()
    
    def get_recent_payments(self, obj):
        from apps.payments.models import PaymentRequestItem
        items = PaymentRequestItem.objects.filter(
            supplier=obj
        ).select_related('payment_request').order_by('-created_at')[:5]
        return [{
            'id': item.payment_request.id,
            'amount': str(item.amount),
            'status': item.payment_request.status,
            'date': item.created_at.strftime('%Y-%m-%d')
        } for item in items]
