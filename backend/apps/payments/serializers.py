"""
طلبات الدفع - Serializers
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import PaymentRequest, PaymentRequestItem, AuditLog

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer للمستخدم"""
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name', 'email']
    
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class PaymentRequestItemSerializer(serializers.ModelSerializer):
    """Serializer لبند طلب الدفع"""
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    supplier_code = serializers.CharField(source='supplier.code', read_only=True)
    sultan_approval_display = serializers.CharField(source='get_sultan_approval_display', read_only=True)
    auditor_status_display = serializers.CharField(source='get_auditor_status_display', read_only=True)
    cfo_approval_display = serializers.CharField(source='get_cfo_approval_display', read_only=True)
    abu_alaa_final_display = serializers.CharField(source='get_abu_alaa_final_display', read_only=True)
    
    class Meta:
        model = PaymentRequestItem
        fields = [
            'id', 'payment_request', 'supplier', 'supplier_name', 'supplier_code',
            'current_balance', 'amount', 'proposed_amount', 'abu_alaa_proposed',
            'sultan_approval', 'sultan_approval_display',
            'auditor_status', 'auditor_status_display',
            'cfo_approval', 'cfo_approval_display',
            'abu_alaa_final', 'abu_alaa_final_display',
            'invoice_number', 'invoice_date', 'description', 'notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer لسجل المراجعة"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'action', 'old_status', 'new_status',
            'notes', 'created_at'
        ]


class PaymentRequestListSerializer(serializers.ModelSerializer):
    """Serializer مختصر لقائمة طلبات الدفع"""
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='')
    bank_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, default=0
    )
    
    class Meta:
        model = PaymentRequest
        fields = [
            'id', 'branch', 'branch_name', 'bank', 'bank_name',
            'amount', 'total_amount', 'status', 'status_display',
            'items_count', 'created_by_name',
            'created_at', 'updated_at'
        ]
    
    def get_bank_name(self, obj):
        return obj.bank.name if obj.bank else ''
    
    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else ''


class PaymentRequestDetailSerializer(serializers.ModelSerializer):
    """Serializer تفصيلي لطلب الدفع"""
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='')
    bank_name = serializers.SerializerMethodField()
    created_by = UserSerializer(read_only=True)
    proposed_by = UserSerializer(read_only=True)
    first_approved_by = UserSerializer(read_only=True)
    audited_by = UserSerializer(read_only=True)
    final_approved_by = UserSerializer(read_only=True)
    status_display = serializers.CharField(read_only=True)
    items = PaymentRequestItemSerializer(many=True, read_only=True)
    audit_logs = AuditLogSerializer(many=True, read_only=True)
    available_transitions = serializers.SerializerMethodField()
    
    class Meta:
        model = PaymentRequest
        fields = [
            'id', 'branch', 'branch_name', 'bank', 'bank_name',
            'amount', 'current_balance',
            'analytical_account', 'supplier_account', 'cost_center',
            'bank_account_number', 'bank_code',
            'status', 'status_display', 'notes', 'rejection_reason',
            'created_by', 'proposed_by', 'first_approved_by',
            'audited_by', 'final_approved_by',
            'created_at', 'updated_at',
            'proposed_at', 'first_approved_at', 'audited_at', 'final_approved_at',
            'items', 'audit_logs', 'available_transitions'
        ]
    
    def get_bank_name(self, obj):
        return obj.bank.name if obj.bank else ''
    
    def get_available_transitions(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.get_available_transitions(request.user)
        return []


class PaymentRequestCreateSerializer(serializers.ModelSerializer):
    """Serializer لإنشاء طلب دفع جديد"""
    items = PaymentRequestItemSerializer(many=True, required=False)
    
    class Meta:
        model = PaymentRequest
        fields = [
            'branch', 'bank',
            'analytical_account', 'supplier_account', 'cost_center',
            'bank_account_number', 'bank_code',
            'notes', 'items'
        ]
    
    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        request = self.context.get('request')
        
        payment_request = PaymentRequest.objects.create(
            created_by=request.user,
            **validated_data
        )
        
        for item_data in items_data:
            PaymentRequestItem.objects.create(
                payment_request=payment_request,
                **item_data
            )
        
        # تحديث المبلغ الإجمالي
        payment_request.amount = payment_request.total_amount
        payment_request.save()
        
        return payment_request


class PaymentTransitionSerializer(serializers.Serializer):
    """Serializer لتغيير حالة طلب الدفع"""
    status = serializers.ChoiceField(choices=PaymentRequest.Status.choices)
    notes = serializers.CharField(required=False, allow_blank=True)


class BulkPaymentItemInputSerializer(serializers.Serializer):
    """Serializer مبسط لإدخال بند واحد في الإنشاء المجمع"""
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=PaymentRequestItem._meta.get_field('supplier').related_model.objects.all()
    )
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    proposed_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    abu_alaa_proposed = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=0)
    sultan_approval = serializers.ChoiceField(
        choices=PaymentRequestItem.ApprovalStatus.choices, 
        required=False, 
        default='pending'
    )
    auditor_status = serializers.ChoiceField(
        choices=PaymentRequestItem.ApprovalStatus.choices, 
        required=False, 
        default='pending'
    )
    cfo_approval = serializers.ChoiceField(
        choices=PaymentRequestItem.ApprovalStatus.choices, 
        required=False, 
        default='pending'
    )
    abu_alaa_final = serializers.ChoiceField(
        choices=PaymentRequestItem.ApprovalStatus.choices, 
        required=False, 
        default='pending'
    )


class BulkPaymentItemCreateSerializer(serializers.Serializer):
    """Serializer لإنشاء عدة بنود دفع دفعة واحدة"""
    items = BulkPaymentItemInputSerializer(many=True)
    
    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("يجب إضافة بند واحد على الأقل")
        return value
    
    def create(self, validated_data):
        items_data = validated_data.get('items', [])
        request = self.context.get('request')
        branch = None
        
        # الحصول على الفرع من أول مورد
        if items_data and 'supplier' in items_data[0]:
            supplier = items_data[0].get('supplier')
            if hasattr(supplier, 'branch'):
                branch = supplier.branch
        
        # إنشاء طلب دفع جديد
        from apps.branches.models import Branch
        if not branch:
            branch = Branch.objects.filter(is_active=True).first()
        
        payment_request = PaymentRequest.objects.create(
            branch=branch,
            created_by=request.user,
            status=PaymentRequest.Status.DRAFT
        )
        
        # إنشاء البنود
        for item_data in items_data:
            # إذا لم يكن هناك proposed_amount، استخدم amount
            if 'proposed_amount' not in item_data or item_data['proposed_amount'] is None:
                item_data['proposed_amount'] = item_data['amount']
            
            PaymentRequestItem.objects.create(
                payment_request=payment_request,
                **item_data
            )
        
        # تحديث المبلغ الإجمالي
        payment_request.amount = payment_request.total_amount
        payment_request.save()
        
        return payment_request


class DashboardStatsSerializer(serializers.Serializer):
    """Serializer لإحصائيات لوحة التحكم"""
    branches_count = serializers.IntegerField()
    suppliers_count = serializers.IntegerField()
    banks_count = serializers.IntegerField()
    total_payments = serializers.DecimalField(max_digits=14, decimal_places=2)
    pending_payments = serializers.IntegerField()
    approved_payments = serializers.IntegerField()
    rejected_payments = serializers.IntegerField()
    today_payments = serializers.IntegerField()
    this_month_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    status_distribution = serializers.ListField()
    monthly_payments = serializers.ListField()
    top_suppliers = serializers.ListField()
    recent_payments = PaymentRequestListSerializer(many=True)
