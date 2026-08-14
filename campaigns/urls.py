from django.urls import path

from . import views

app_name = 'campaigns'

urlpatterns = [
    path('', views.CampaignListView.as_view(), name='list'),
    path('nova/', views.CampaignCreateView.as_view(), name='create'),
    path('<int:pk>/', views.CampaignDetailView.as_view(), name='detail'),
    path('<int:pk>/iniciar/', views.CampaignStartView.as_view(), name='start'),
    path('<int:pk>/pausar/', views.CampaignPauseView.as_view(), name='pause'),
    path('<int:pk>/retomar/', views.CampaignResumeView.as_view(), name='resume'),
    path('<int:pk>/cancelar/', views.CampaignCancelView.as_view(), name='cancel'),
    path('<int:pk>/relatorio/', views.CampaignReportExportView.as_view(), name='report'),
    path('<int:pk>/eventos/', views.CampaignProgressStreamView.as_view(), name='progress_stream'),
]
