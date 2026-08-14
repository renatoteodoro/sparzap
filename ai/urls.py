from django.urls import path

from . import views

app_name = 'ai'

urlpatterns = [
    path('', views.AIConfigListView.as_view(), name='list'),
    path('nova/', views.AIConfigCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.AIConfigUpdateView.as_view(), name='update'),
    path('<int:pk>/remover/', views.AIConfigDeleteView.as_view(), name='delete'),
]
