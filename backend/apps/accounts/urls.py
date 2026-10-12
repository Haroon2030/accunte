from django.urls import path

from . import views

urlpatterns = [
    path('auth/me/', views.me),
    path('auth/login/', views.login_view),
    path('auth/logout/', views.logout_view),
    path('auth/change-password/', views.change_password),
    path('users/', views.users_collection),
    path('users/<int:pk>/', views.user_update),
    path('users/<int:pk>/toggle/', views.user_toggle),
    path('users/<int:pk>/reset-password/', views.user_reset_password),
]
