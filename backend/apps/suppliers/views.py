"""
الموردين - API Views
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum

from .models import Supplier
from .serializers import SupplierSerializer, SupplierListSerializer, SupplierDetailSerializer


class SupplierViewSet(viewsets.ModelViewSet):
    """
    ViewSet لإدارة الموردين
    """
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'code', 'phone', 'email']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SupplierDetailSerializer
        return SupplierSerializer

    @action(detail=False, methods=['get'])
    def active(self, request):
        """الحصول على الموردين النشطين فقط"""
        queryset = self.queryset.filter(is_active=True)
        serializer = SupplierListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def all(self, request):
        """جلب جميع الموردين دفعة واحدة للقوائم المنسدلة"""
        queryset = self.queryset.filter(is_active=True).only('id', 'name', 'code').order_by('name')
        serializer = SupplierListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """بحث سريع عن مورد"""
        q = request.query_params.get('q', '')
        if len(q) < 2:
            return Response([])
        
        queryset = self.queryset.filter(
            is_active=True
        ).filter(
            models.Q(name__icontains=q) | models.Q(code__icontains=q)
        )[:10]
        
        serializer = SupplierListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def payment_history(self, request, pk=None):
        """تاريخ مدفوعات المورد"""
        supplier = self.get_object()
        from apps.payments.models import PaymentRequestItem
        from apps.payments.serializers import PaymentRequestItemSerializer
        
        items = PaymentRequestItem.objects.filter(
            supplier=supplier
        ).select_related('payment_request').order_by('-created_at')
        
        serializer = PaymentRequestItemSerializer(items, many=True)
        return Response(serializer.data)
