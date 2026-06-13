"""
إيجارات المساحات - API Views
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import SpaceRental
from .serializers import SpaceRentalSerializer


class SpaceRentalViewSet(viewsets.ModelViewSet):
    """ViewSet لإدارة إيجارات المساحات"""

    queryset = SpaceRental.objects.select_related('branch', 'supplier').all()
    serializer_class = SpaceRentalSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['branch', 'supplier', 'is_active']
    search_fields = ['code', 'title', 'supplier__name', 'branch__name']
    ordering_fields = ['title', 'code', 'monthly_rent', 'start_date', 'created_at']
    ordering = ['-created_at']

    @action(detail=False, methods=['get'])
    def active(self, request):
        queryset = self.queryset.filter(is_active=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
