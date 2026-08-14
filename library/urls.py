from django.urls import path

from . import views

app_name = 'library'

urlpatterns = [
    path('', views.MessageListView.as_view(), name='list'),
    path('nova/', views.MessageCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.MessageUpdateView.as_view(), name='update'),
    path('<int:pk>/remover/', views.MessageDeleteView.as_view(), name='delete'),
    path('<int:pk>/preview/', views.MessagePreviewView.as_view(), name='preview'),
    path('pastas/nova/', views.MessageFolderCreateView.as_view(), name='folder_create'),
    path('pastas/<int:pk>/remover/', views.MessageFolderDeleteView.as_view(), name='folder_delete'),
]
