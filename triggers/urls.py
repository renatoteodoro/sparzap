from django.urls import path

from . import views

app_name = 'triggers'

urlpatterns = [
    path('', views.TriggerListView.as_view(), name='list'),
    path('novo/', views.TriggerCreateView.as_view(), name='create'),
    path('<int:pk>/editar/', views.TriggerUpdateView.as_view(), name='update'),
    path('<int:pk>/remover/', views.TriggerDeleteView.as_view(), name='delete'),
    path('testar/', views.TriggerTestView.as_view(), name='test'),
    path('logs/', views.TriggerLogListView.as_view(), name='logs'),
    path('agendadas/', views.ScheduledMsgListView.as_view(), name='scheduled_list'),
    path('agendadas/<int:pk>/cancelar/', views.ScheduledMsgCancelView.as_view(), name='scheduled_cancel'),
    path('agendadas/<int:pk>/reagendar/', views.ScheduledMsgRescheduleView.as_view(), name='scheduled_reschedule'),
    path('agendar/<int:contact_pk>/', views.ScheduledMsgCreateForLeadView.as_view(), name='scheduled_create'),
]
