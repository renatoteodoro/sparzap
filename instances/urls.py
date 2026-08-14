from django.urls import path

from . import views

app_name = 'instances'

urlpatterns = [
    path('', views.InstanceListView.as_view(), name='list'),
    path('nova/', views.InstanceCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.InstanceUpdateView.as_view(), name='update'),
    path('<int:pk>/remover/', views.InstanceDeleteView.as_view(), name='delete'),
    path('<int:pk>/conectar/', views.InstanceConnectView.as_view(), name='connect'),
    path('<int:pk>/status/', views.InstanceRefreshStatusView.as_view(), name='refresh_status'),
    path('<int:pk>/teste/', views.InstanceTestMessageView.as_view(), name='test_message'),
    path('<int:pk>/desativar/', views.InstanceDeactivateView.as_view(), name='deactivate'),
]
