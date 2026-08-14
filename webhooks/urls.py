from django.urls import path

from . import views

app_name = 'webhooks'

urlpatterns = [
    path('evolution/<str:instance_name>/', views.receive_webhook, name='evolution'),
]
