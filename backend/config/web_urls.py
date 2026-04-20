"""
Web URLs - روابط واجهة الويب
"""
from django.urls import path, include
from apps.core import web_views

# Authentication URLs
auth_patterns = [
    path('login/', web_views.login_view, name='login'),
    path('logout/', web_views.logout_view, name='logout'),
]

# Branch URLs
branch_patterns = [
    path('', web_views.BranchListView.as_view(), name='list'),
    path('create/', web_views.branch_create, name='create'),
    path('<int:pk>/update/', web_views.branch_update, name='update'),
    path('<int:pk>/delete/', web_views.branch_delete, name='delete'),
]

# Bank URLs
bank_patterns = [
    path('', web_views.BankListView.as_view(), name='list'),
    path('create/', web_views.bank_create, name='create'),
    path('<int:pk>/update/', web_views.bank_update, name='update'),
    path('<int:pk>/delete/', web_views.bank_delete, name='delete'),
]

# Cost Center URLs
cost_center_patterns = [
    path('', web_views.CostCenterListView.as_view(), name='list'),
    path('create/', web_views.cost_center_create, name='create'),
    path('<int:pk>/update/', web_views.cost_center_update, name='update'),
    path('<int:pk>/delete/', web_views.cost_center_delete, name='delete'),
]

# Supplier URLs
supplier_patterns = [
    path('', web_views.SupplierListView.as_view(), name='list'),
    path('create/', web_views.supplier_create, name='create'),
    path('<int:pk>/update/', web_views.supplier_update, name='update'),
    path('<int:pk>/delete/', web_views.supplier_delete, name='delete'),
]

# Payment URLs
payment_patterns = [
    path('', web_views.PaymentListView.as_view(), name='list'),
    path('create/', web_views.payment_create, name='create'),
    path('<int:pk>/', web_views.PaymentDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', web_views.payment_update, name='update'),
    path('<int:pk>/status/', web_views.payment_change_status, name='change_status'),
    path('<int:pk>/export-excel/', web_views.payment_export_excel, name='export_excel'),
]

# User URLs
user_patterns = [
    path('', web_views.UserListView.as_view(), name='list'),
    path('create/', web_views.user_create, name='create'),
    path('<int:pk>/update/', web_views.user_update, name='update'),
    path('<int:pk>/delete/', web_views.user_delete, name='delete'),
]

# Main URL patterns
urlpatterns = [
    # Dashboard
    path('', web_views.dashboard_view, name='dashboard'),
    
    # Auth
    path('auth/', include((auth_patterns, 'auth'))),
    
    # CRUD
    path('branches/', include((branch_patterns, 'branches'))),
    path('banks/', include((bank_patterns, 'banks'))),
    path('cost-centers/', include((cost_center_patterns, 'cost_centers'))),
    path('suppliers/', include((supplier_patterns, 'suppliers'))),
    path('payments/', include((payment_patterns, 'payments'))),
    path('users/', include((user_patterns, 'users'))),
]
