"""
طلبات الدفع - API Views
"""
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta

from .models import PaymentRequest, PaymentRequestItem, AuditLog
from .serializers import (
    PaymentRequestListSerializer,
    PaymentRequestDetailSerializer,
    PaymentRequestCreateSerializer,
    PaymentRequestItemSerializer,
    PaymentTransitionSerializer,
    AuditLogSerializer,
    DashboardStatsSerializer,
    BulkPaymentItemCreateSerializer
)
from apps.branches.models import Branch
from apps.banks.models import Bank
from apps.suppliers.models import Supplier


class PaymentRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet لإدارة طلبات الدفع
    مع فلترة حسب صلاحيات المستخدم
    """
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'branch', 'bank']
    search_fields = ['id', 'branch__name', 'notes']
    ordering_fields = ['created_at', 'amount', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        فلترة البيانات حسب صلاحيات المستخدم:
        - موظف فرع: يرى فقط طلبات فرعه
        - مدقق/مدير/ادمن: يرون جميع الطلبات
        """
        queryset = PaymentRequest.objects.select_related(
            'branch', 'bank', 'created_by'
        ).prefetch_related('items')
        
        user = self.request.user
        
        # إذا كان المستخدم غير مسجل، يرى كل البيانات (للاختبار)
        if not user.is_authenticated:
            return queryset
        
        # التحقق من وجود UserProfile
        if hasattr(user, 'profile'):
            profile = user.profile
            
            # موظف الفرع يرى فقط طلبات فرعه
            if profile.is_branch_employee and not profile.can_see_all_branches:
                if profile.branch:
                    queryset = queryset.filter(branch=profile.branch)
                else:
                    # إذا لم يكن مرتبط بفرع، لا يرى شيء
                    queryset = queryset.none()
        
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return PaymentRequestListSerializer
        elif self.action == 'create':
            return PaymentRequestCreateSerializer
        return PaymentRequestDetailSerializer

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        """تغيير حالة طلب الدفع"""
        payment = self.get_object()
        serializer = PaymentTransitionSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        new_status = serializer.validated_data['status']
        notes = serializer.validated_data.get('notes', '')
        
        # التحقق من صلاحية الانتقال
        available_transitions = payment.get_available_transitions(request.user)
        valid_statuses = [t['status'] for t in available_transitions]
        
        if new_status not in valid_statuses:
            return Response(
                {'error': 'لا يمكنك تنفيذ هذا الإجراء'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # حفظ الحالة القديمة
        old_status = payment.status
        
        # تحديث الحالة
        payment.status = new_status
        now = timezone.now()
        
        if new_status == PaymentRequest.Status.PROPOSED:
            payment.proposed_by = request.user
            payment.proposed_at = now
        elif new_status == PaymentRequest.Status.FIRST_APPROVED:
            payment.first_approved_by = request.user
            payment.first_approved_at = now
        elif new_status == PaymentRequest.Status.AUDITED:
            payment.audited_by = request.user
            payment.audited_at = now
        elif new_status == PaymentRequest.Status.FINAL_APPROVED:
            payment.final_approved_by = request.user
            payment.final_approved_at = now
        elif new_status == PaymentRequest.Status.REJECTED:
            payment.rejection_reason = notes
        
        payment.save()
        
        # إنشاء سجل مراجعة
        AuditLog.objects.create(
            payment_request=payment,
            user=request.user,
            action=f'تغيير الحالة من {old_status} إلى {new_status}',
            old_status=old_status,
            new_status=new_status,
            notes=notes
        )
        
        return Response(PaymentRequestDetailSerializer(
            payment, context={'request': request}
        ).data)

    @action(detail=True, methods=['get'])
    def audit_log(self, request, pk=None):
        """الحصول على سجل مراجعة الطلب"""
        payment = self.get_object()
        logs = payment.audit_logs.all()
        serializer = AuditLogSerializer(logs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        """إضافة بند جديد للطلب"""
        payment = self.get_object()
        
        if payment.status != PaymentRequest.Status.DRAFT:
            return Response(
                {'error': 'لا يمكن إضافة بنود إلا في حالة المسودة'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = PaymentRequestItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(payment_request=payment)
            
            # تحديث المبلغ الإجمالي
            payment.amount = payment.total_amount
            payment.save()
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """ملخص طلبات الدفع"""
        queryset = self.get_queryset()
        
        total = queryset.aggregate(total=Sum('amount'))['total'] or 0
        by_status = dict(
            queryset.values_list('status').annotate(
                count=Count('id')
            ).values_list('status', 'count')
        )
        
        return Response({
            'total_amount': total,
            'total_count': queryset.count(),
            'by_status': by_status
        })


class DashboardView(APIView):
    """
    لوحة التحكم - إحصائيات عامة
    مع فلترة حسب صلاحيات المستخدم
    """
    permission_classes = [AllowAny]
    
    def get_user_branch(self, user):
        """الحصول على فرع المستخدم إذا كان موظف فرع"""
        if not user.is_authenticated:
            return None
        if hasattr(user, 'profile'):
            profile = user.profile
            if profile.is_branch_employee and not profile.can_see_all_branches:
                return profile.branch
        return None
    
    def get(self, request):
        user = request.user
        user_branch = self.get_user_branch(user)
        
        # الإحصائيات الأساسية
        branches_count = Branch.objects.filter(is_active=True).count()
        suppliers_count = Supplier.objects.filter(is_active=True).count()
        banks_count = Bank.objects.filter(is_active=True).count()
        
        # فلترة الطلبات حسب صلاحيات المستخدم
        payments_qs = PaymentRequest.objects.all()
        if user_branch:
            payments_qs = payments_qs.filter(branch=user_branch)
        
        total_payments = payments_qs.aggregate(total=Sum('amount'))['total'] or 0
        
        # عدد الطلبات حسب الحالة
        status_counts = dict(
            payments_qs.values_list('status').annotate(
                count=Count('id')
            ).values_list('status', 'count')
        )
        
        pending_payments = (
            status_counts.get('draft', 0) + 
            status_counts.get('proposed', 0)
        )
        approved_payments = status_counts.get('final_approved', 0)
        rejected_payments = status_counts.get('rejected', 0)
        
        # توزيع الحالات
        status_labels = dict(PaymentRequest.Status.choices)
        status_colors = {
            'draft': '#64748b',
            'proposed': '#3b82f6',
            'first_approved': '#f59e0b',
            'audited': '#8b5cf6',
            'final_approved': '#10b981',
            'rejected': '#ef4444',
        }
        status_distribution = [
            {
                'status': code,
                'label': status_labels.get(code, code),
                'count': count,
                'color': status_colors.get(code, '#6b7280')
            }
            for code, count in status_counts.items()
        ]
        
        # المدفوعات الشهرية (آخر 6 أشهر)
        six_months_ago = timezone.now() - timedelta(days=180)
        monthly_data = (
            payments_qs
            .filter(created_at__gte=six_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('month')
        )
        monthly_payments = [
            {
                'month': item['month'].strftime('%Y-%m') if item['month'] else '',
                'month_name': item['month'].strftime('%B %Y') if item['month'] else '',
                'total': float(item['total'] or 0),
                'count': item['count']
            }
            for item in monthly_data
        ]
        
        # أفضل الموردين (مع فلترة حسب فرع المستخدم)
        top_suppliers_qs = PaymentRequestItem.objects.all()
        if user_branch:
            top_suppliers_qs = top_suppliers_qs.filter(payment_request__branch=user_branch)
        
        top_suppliers = list(
            top_suppliers_qs
            .values('supplier__name', 'supplier__code')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')[:10]
        )
        top_suppliers = [
            {
                'name': s['supplier__name'],
                'code': s['supplier__code'],
                'total': float(s['total'] or 0),
                'count': s['count']
            }
            for s in top_suppliers
        ]
        
        # إحصائيات اليوم والشهر
        today = timezone.now().date()
        today_payments = payments_qs.filter(created_at__date=today).count()
        this_month_total = payments_qs.filter(
            created_at__year=today.year,
            created_at__month=today.month
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # آخر الطلبات
        recent_payments = payments_qs.select_related(
            'branch', 'bank', 'created_by'
        ).annotate(
            items_count=Count('items'),
            total_amount=Sum('items__amount')
        )[:10]
        
        data = {
            'branches_count': branches_count,
            'suppliers_count': suppliers_count,
            'banks_count': banks_count,
            'total_payments': float(total_payments),
            'pending_payments': pending_payments,
            'approved_payments': approved_payments,
            'rejected_payments': rejected_payments,
            'today_payments': today_payments,
            'this_month_total': float(this_month_total),
            'status_distribution': status_distribution,
            'monthly_payments': monthly_payments,
            'top_suppliers': top_suppliers,
            'recent_payments': PaymentRequestListSerializer(
                recent_payments, many=True
            ).data,
        }
        
        return Response(data)


class PaymentRequestItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet لإدارة بنود الدفع
    مع تقييد تعديل حالة التدقيق للمدققين والأدمن فقط
    """
    # permission_classes = [IsAuthenticated]  # Disabled for testing
    serializer_class = PaymentRequestItemSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['payment_request', 'sultan_approval', 'auditor_status', 'cfo_approval', 'abu_alaa_final']
    search_fields = ['supplier__name', 'supplier__code', 'invoice_number']
    ordering_fields = ['created_at', 'amount', 'supplier__name']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        فلترة البيانات حسب صلاحيات المستخدم
        """
        queryset = PaymentRequestItem.objects.select_related('supplier', 'payment_request', 'payment_request__branch')
        
        user = self.request.user
        
        # إذا كان المستخدم غير مسجل، يرى كل البيانات (للاختبار)
        if not user.is_authenticated:
            return queryset
        
        # التحقق من وجود UserProfile
        if hasattr(user, 'profile'):
            profile = user.profile
            
            # موظف الفرع يرى فقط بنود طلبات فرعه
            if profile.is_branch_employee and not profile.can_see_all_branches:
                if profile.branch:
                    queryset = queryset.filter(payment_request__branch=profile.branch)
                else:
                    queryset = queryset.none()
        
        return queryset

    def update(self, request, *args, **kwargs):
        """
        التحقق من صلاحيات تعديل حالة التدقيق
        """
        instance = self.get_object()
        
        # التحقق من تعديل حالة التدقيق
        if 'auditor_status' in request.data:
            user = request.user
            can_edit = False
            
            if hasattr(user, 'profile'):
                can_edit = user.profile.can_edit_auditor_status
            
            # السماح للسوبر يوزر
            if user.is_superuser:
                can_edit = True
            
            if not can_edit:
                return Response(
                    {'error': 'ليس لديك صلاحية لتغيير حالة التدقيق'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """
        التحقق من صلاحيات تعديل حالة التدقيق
        """
        # التحقق من تعديل حالة التدقيق
        if 'auditor_status' in request.data:
            user = request.user
            can_edit = False
            
            if hasattr(user, 'profile'):
                can_edit = user.profile.can_edit_auditor_status
            
            # السماح للسوبر يوزر
            if user.is_superuser:
                can_edit = True
            
            if not can_edit:
                return Response(
                    {'error': 'ليس لديك صلاحية لتغيير حالة التدقيق'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """إنشاء عدة بنود دفع دفعة واحدة"""
        serializer = BulkPaymentItemCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            payment_request = serializer.save()
            return Response({
                'message': 'تم إنشاء طلب الدفع بنجاح',
                'payment_request_id': payment_request.id,
                'items_count': payment_request.items.count()
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
