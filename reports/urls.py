from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.ReportsIndexView.as_view(), name='index'),
    path('entregas/exportar/', views.DeliveryReportExportView.as_view(), name='delivery_export'),
    path('backup/', views.BackupView.as_view(), name='backup'),
    path('backup/exportar/', views.BackupExportView.as_view(), name='backup_export'),
    path('backup/importar/', views.BackupImportView.as_view(), name='backup_import'),
]
