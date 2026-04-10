"""
نظام إدارة المدفوعات - URL Configuration
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from apps.core.views import admin_frontend

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # API v1
    path('api/v1/', include('config.api_urls')),
    
    # JWT Authentication
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # API Documentation (Swagger/OpenAPI)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # React Frontend pages
    path('', admin_frontend, name='frontend-home'),
    path('login', admin_frontend),
    path('permissions', admin_frontend),
    path('permissions/', admin_frontend),
    path('users', admin_frontend),
    path('users/', admin_frontend),
    path('audit-log', admin_frontend),
    path('audit-log/', admin_frontend),
    path('banks', admin_frontend),
    path('banks/', admin_frontend),
    path('branches', admin_frontend),
    path('branches/', admin_frontend),
    path('suppliers', admin_frontend),
    path('suppliers/', admin_frontend),
    path('cost-centers', admin_frontend),
    path('cost-centers/', admin_frontend),
    path('payments', admin_frontend),
    path('payments/', admin_frontend),
    path('payments/<path:path>', admin_frontend),
    path('settings', admin_frontend),
    path('settings/', admin_frontend),
    path('reports', admin_frontend),
    path('reports/', admin_frontend),
]

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
