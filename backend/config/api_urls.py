"""
API URLs - v1
نظام إدارة المدفوعات
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.branches.views import BranchViewSet
from apps.banks.views import BankViewSet
from apps.cost_centers.views import CostCenterViewSet
from apps.suppliers.views import SupplierViewSet
from apps.payments.views import PaymentRequestViewSet, PaymentRequestItemViewSet, DashboardView
from apps.core.views import PermissionViewSet, RoleViewSet, UserViewSet, current_user

# Create router
router = DefaultRouter()
router.register(r'branches', BranchViewSet, basename='branch')
router.register(r'banks', BankViewSet, basename='bank')
router.register(r'cost-centers', CostCenterViewSet, basename='cost-center')
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'payments', PaymentRequestViewSet, basename='payment')
router.register(r'payment-items', PaymentRequestItemViewSet, basename='payment-item')
router.register(r'permissions', PermissionViewSet, basename='permission')
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    # ViewSets
    path('', include(router.urls)),
    
    # Dashboard
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    
    # Current User
    path('me/', current_user, name='current-user'),
]
