from django.urls import path

from . import views as v

urlpatterns = [
    path('auth/me', v.MeView.as_view()),
    path('auth/login', v.LoginView.as_view()),
    path('auth/logout', v.LogoutView.as_view()),
    path('auth/change-password', v.ChangePasswordView.as_view()),

    path('users/', v.UsersView.as_view()),
    path('users/<int:pk>/', v.UserDetailView.as_view()),
    path('users/<int:pk>/toggle', v.UserToggleView.as_view()),
    path('users/<int:pk>/reset-password', v.UserResetView.as_view()),

    path('changes/', v.ChangesView.as_view()),
    path('matchers/', v.MatchersView.as_view()),
    path('requests/', v.RequestsView.as_view()),
    path('requests/<int:pk>/', v.RequestDetailView.as_view()),
    path('requests/<int:pk>/advance', v.RequestAdvanceView.as_view()),
    path('requests/<int:pk>/messages', v.RequestMessagesView.as_view()),

    path('complaints/', v.ComplaintsView.as_view()),
    path('complaints/<int:pk>/', v.ComplaintDetailView.as_view()),
    path('complaints/<int:pk>/advance', v.ComplaintAdvanceView.as_view()),
    path('complaints/<int:pk>/messages', v.ComplaintMessagesView.as_view()),

    path('attachments/<int:pk>/download/', v.AttachmentDownloadView.as_view()),
]
