from django.urls import path

from . import views

app_name = 'crm'

urlpatterns = [
    path('', views.KanbanView.as_view(), name='kanban'),
    path('leads/', views.LeadListView.as_view(), name='list'),
    path('leads/exportar/', views.LeadExportView.as_view(), name='export'),
    path('leads/<int:pk>/', views.LeadDetailView.as_view(), name='detail'),
    path('leads/<int:pk>/mover/', views.LeadMoveView.as_view(), name='move'),
    path('leads/<int:pk>/anotar/', views.LeadNoteCreateView.as_view(), name='note_create'),
]
