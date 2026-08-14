from django.urls import path

from . import views

app_name = 'scripts'

urlpatterns = [
    path('', views.ScriptListView.as_view(), name='list'),
    path('novo/', views.ScriptCreateView.as_view(), name='create'),
    path('<int:pk>/', views.ScriptDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.ScriptUpdateView.as_view(), name='update'),
    path('<int:pk>/remover/', views.ScriptDeleteView.as_view(), name='delete'),
    path('<int:pk>/duplicar/', views.ScriptDuplicateView.as_view(), name='duplicate'),
    path('<int:pk>/testar/', views.ScriptTestRunView.as_view(), name='test_run'),
    path('<int:script_pk>/passos/novo/', views.ScriptStepCreateView.as_view(), name='step_create'),
    path('<int:script_pk>/passos/<int:pk>/remover/', views.ScriptStepDeleteView.as_view(), name='step_delete'),
]
