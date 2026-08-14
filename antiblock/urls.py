from django.urls import path

from . import views

app_name = 'antiblock'

urlpatterns = [
    path('', views.WarmupListView.as_view(), name='warmup'),
    path('<int:instance_pk>/iniciar/', views.WarmupStartView.as_view(), name='warmup_start'),
    path('planos/<int:pk>/pausar/', views.WarmupPauseView.as_view(), name='warmup_pause'),
    path('planos/<int:pk>/retomar/', views.WarmupResumeView.as_view(), name='warmup_resume'),
]
