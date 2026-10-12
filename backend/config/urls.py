"""
مسارات المشروع: الواجهة الثابتة تُقدَّم من نفس النطاق، والـ API تحت /api/ بجلسات وCSRF.
  /          واجهة الموظفين (المطابق، المدير المالي، مدير النظام)
  /portal/   بوابة الموردين (وكذلك /supplier/)
  /api/...   JSON
  /admin/    لوحة Django (حساب مدير النظام)
"""
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path('', views.staff_page, name='staff'),
    path('portal/', views.supplier_page, name='portal'),
    path('supplier/', views.supplier_page),
    path('healthz', views.healthz),
    path('admin/', admin.site.urls),
    path('api/', include('apps.accounts.urls')),
    path('api/', include('apps.matching.urls')),
]
