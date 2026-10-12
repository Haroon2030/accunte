from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

urlpatterns = [
    path('healthz', lambda request: HttpResponse('ok', content_type='text/plain')),
    path('django-admin/', admin.site.urls),
    path('api/', include('portal.urls')),
]
