"""
البنوك - API Views
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Bank
from .serializers import BankSerializer, BankListSerializer


class BankViewSet(viewsets.ModelViewSet):
    """
    ViewSet لإدارة البنوك
    """
    queryset = Bank.objects.select_related('branch')
    serializer_class = BankSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'branch']
    search_fields = ['name', 'code', 'account_number']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']

    @action(detail=False, methods=['get'])
    def active(self, request):
        """الحصول على البنوك النشطة فقط"""
        queryset = self.queryset.filter(is_active=True)
        serializer = BankListSerializer(queryset, many=True)
        return Response(serializer.data)
