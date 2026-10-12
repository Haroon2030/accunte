from django.urls import path

from . import views

urlpatterns = [
    path('bootstrap/', views.bootstrap),
    path('requests/', views.request_create),
    path('requests/<str:code>/advance/', views.request_advance),
    path('requests/<str:code>/messages/', views.request_message),
    path('complaints/', views.complaint_create),
    path('complaints/<str:code>/advance/', views.complaint_advance),
    path('complaints/<str:code>/messages/', views.complaint_message),
    path('seen/', views.mark_seen),
    path('attachments/<int:pk>/', views.attachment_download),
]
