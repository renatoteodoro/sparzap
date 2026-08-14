from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('cadastro/', views.SignupView.as_view(), name='signup'),
    path('entrar/', views.EmailLoginView.as_view(), name='login'),
    path('sair/', views.EmailLogoutView.as_view(), name='logout'),
    path(
        'senha/redefinir/',
        auth_views.PasswordResetView.as_view(
            template_name='accounts/password_reset.html',
            email_template_name='accounts/password_reset_email.html',
            success_url='/contas/senha/redefinir/enviado/',
        ),
        name='password_reset',
    ),
    path(
        'senha/redefinir/enviado/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'senha/redefinir/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            success_url='/contas/senha/redefinir/concluido/',
        ),
        name='password_reset_confirm',
    ),
    path(
        'senha/redefinir/concluido/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
]
