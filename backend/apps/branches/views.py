"""
الفروع - API Views
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count

from .models import Branch
from .serializers import BranchSerializer, BranchListSerializer, BranchDetailSerializer


class BranchViewSet(viewsets.ModelViewSet):
    """
    ViewSet لإدارة الفروع
    """
    queryset = Branch.objects.select_related('cost_center').annotate(
        banks_count=Count('bank_accounts', distinct=True),
        payments_count=Count('payment_requests', distinct=True)
    )
    serializer_class = BranchSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'cost_center']
    search_fields = ['name', 'code', 'address']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BranchDetailSerializer
        return BranchSerializer

    @action(detail=False, methods=['get'])
    def active(self, request):
        """الحصول على الفروع النشطة فقط"""
        queryset = self.queryset.filter(is_active=True)
        serializer = BranchListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        """الحصول على طلبات الدفع للفرع"""
        branch = self.get_object()
        from apps.payments.serializers import PaymentRequestListSerializer
        payments = branch.payment_requests.all()[:20]
        serializer = PaymentRequestListSerializer(payments, many=True)
        return Response(serializer.data)
