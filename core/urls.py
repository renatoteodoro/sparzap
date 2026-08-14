"""
URL raiz do Sparzap. O pacote `core` acumula o papel de projeto Django
(settings/wsgi/asgi/celery) e de app "de casa" (landing pública, dashboard,
BaseModel) — por isso as rotas de `core` são declaradas aqui mesmo, sem
namespace, e as demais apps entram via include() com namespace próprio.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('healthz/', views.healthz, name='healthz'),
    path('', views.LandingView.as_view(), name='landing'),
    path('painel/', views.DashboardView.as_view(), name='dashboard'),
    path('contas/', include('accounts.urls')),
    path('instancias/', include('instances.urls')),
    path('webhooks/', include('webhooks.urls')),
    path('contatos/', include('contacts.urls')),
    path('mensagens/', include('library.urls')),
    path('scripts/', include('scripts.urls')),
    path('campanhas/', include('campaigns.urls')),
    path('gatilhos/', include('triggers.urls')),
    path('crm/', include('crm.urls')),
    path('relatorios/', include('reports.urls')),
    path('aquecimento/', include('antiblock.urls')),
    path('api/', include('api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
