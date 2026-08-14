from django.urls import include, path

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views

app_name = 'api'

router = DefaultRouter()
router.register('instances', views.InstanceViewSet, basename='instance')
router.register('campaigns', views.CampaignViewSet, basename='campaign')
router.register('contacts', views.ContactViewSet, basename='contact')
router.register('leads', views.LeadViewSet, basename='lead')
router.register('messages/schedule', views.ScheduleMessageView, basename='schedule-message')

urlpatterns = [
    path('token/', obtain_auth_token, name='token'),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/docs/', SpectacularSwaggerView.as_view(url_name='api:schema'), name='swagger'),
    path('', include(router.urls)),
]
