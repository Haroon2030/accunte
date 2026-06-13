"""
الأصناف - API Views
"""
from django.db.models import Count, Sum
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Item, ItemBatch
from .serializers import ItemSerializer, ItemBatchSerializer


class ItemBatchViewSet(viewsets.ModelViewSet):
    """ViewSet لإدارة ملفات الأصناف"""

    queryset = ItemBatch.objects.select_related('supplier', 'created_by').prefetch_related('items').annotate(
        items_count=Count('items'),
        total_amount=Sum('items__amount'),
    )
    serializer_class = ItemBatchSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier']
    search_fields = ['supplier__name', 'items__barcode', 'items__name']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ItemViewSet(viewsets.ModelViewSet):
    """ViewSet لإدارة الأصناف"""

    queryset = Item.objects.select_related('batch__supplier').all()
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['batch', 'is_active']
    search_fields = ['barcode', 'name', 'package', 'batch__supplier__name']
    ordering_fields = ['name', 'barcode', 'amount', 'created_at']
    ordering = ['name']

    @action(detail=False, methods=['get'])
    def active(self, request):
        queryset = self.queryset.filter(is_active=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_supplier(self, request):
        supplier_id = request.query_params.get('supplier')
        queryset = self.queryset.filter(is_active=True)
        if supplier_id:
            queryset = queryset.filter(batch__supplier_id=supplier_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
