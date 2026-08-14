from django.urls import path

from . import views

app_name = 'contacts'

urlpatterns = [
    path('', views.ContactListView.as_view(), name='list'),
    path('novo/', views.ContactCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.ContactUpdateView.as_view(), name='update'),
    path('<int:pk>/remover/', views.ContactDeleteView.as_view(), name='delete'),
    path('importar/', views.ContactImportView.as_view(), name='import'),
    path('exportar/', views.ContactExportView.as_view(), name='export'),
    path('opt-out/', views.ContactBulkOptOutView.as_view(), name='bulk_opt_out'),
    path('deduplicar/', views.ContactDedupeView.as_view(), name='dedupe'),
    path('grupos/', views.GroupListView.as_view(), name='groups'),
    path('grupos/sincronizar/<int:instance_pk>/', views.GroupSyncView.as_view(), name='group_sync'),
    path('grupos/<int:pk>/extrair/', views.GroupExtractParticipantsView.as_view(), name='group_extract'),
    path('grupos/<int:pk>/remover-admin/', views.GroupDemoteSelfView.as_view(), name='group_demote'),
    path('grupos/<int:pk>/enviar/', views.GroupSendMessageView.as_view(), name='group_send'),
]
