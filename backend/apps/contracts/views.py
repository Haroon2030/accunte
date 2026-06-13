"""
العقود - API Views
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Contract
from .serializers import ContractSerializer


class ContractViewSet(viewsets.ModelViewSet):
    """ViewSet لإدارة العقود"""

    queryset = Contract.objects.select_related('supplier').all()
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['contract_type', 'supplier', 'is_active']
    search_fields = ['title', 'code', 'supplier__name']
    ordering_fields = ['title', 'code', 'start_date', 'created_at']
    ordering = ['-created_at']

    @action(detail=False, methods=['get'])
    def active(self, request):
        queryset = self.queryset.filter(is_active=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_type(self, request):
        contract_type = request.query_params.get('type')
        queryset = self.queryset.filter(is_active=True)
        if contract_type:
            queryset = queryset.filter(contract_type=contract_type)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
