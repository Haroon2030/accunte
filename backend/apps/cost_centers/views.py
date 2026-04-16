"""
مراكز التكلفة - API Views
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count

from .models import CostCenter
from .serializers import CostCenterSerializer, CostCenterListSerializer


class CostCenterViewSet(viewsets.ModelViewSet):
    """
    ViewSet لإدارة مراكز التكلفة
    
    list: قائمة جميع مراكز التكلفة
    retrieve: تفاصيل مركز تكلفة محدد
    create: إنشاء مركز تكلفة جديد
    update: تحديث مركز تكلفة
    destroy: حذف مركز تكلفة
    """
    queryset = CostCenter.objects.annotate(
        branches_count=Count('branches')
    )
    serializer_class = CostCenterSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']

    @action(detail=False, methods=['get'])
    def active(self, request):
        """الحصول على مراكز التكلفة النشطة فقط (للقوائم المنسدلة)"""
        queryset = self.queryset.filter(is_active=True)
        serializer = CostCenterListSerializer(queryset, many=True)
        return Response(serializer.data)
