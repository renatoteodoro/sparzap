import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView


class LandingView(TemplateView):
    template_name = 'public/landing.html'


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        from django.db.models import Sum

        from antiblock.models import DailyLimit
        from campaigns.models import CampaignContact
        from crm import services as crm_services
        from crm.models import Lead
        from instances.models import Instance

        instancias = Instance.objects.filter(owner=user)
        context['instancias_conectadas'] = instancias.filter(status=Instance.STATUS_CONECTADO).count()
        context['instancias_total'] = instancias.count()

        hoje = timezone.localdate()
        context['envios_hoje'] = (
            DailyLimit.objects.filter(instance__owner=user, data=hoje).aggregate(
                total=Sum('enviadas'),
            )['total']
            or 0
        )

        enviadas = CampaignContact.objects.filter(campaign__owner=user, status=CampaignContact.STATUS_ENVIADA).count()
        respondidas = CampaignContact.objects.filter(
            campaign__owner=user, status=CampaignContact.STATUS_RESPONDIDA
        ).count()
        total_enviado_ou_respondido = enviadas + respondidas
        context['taxa_resposta'] = (
            round(100 * respondidas / total_enviado_ou_respondido, 1) if total_enviado_ou_respondido else None
        )

        pipeline = crm_services.get_or_create_default_pipeline(user)
        stage_novo = pipeline.stages.filter(nome='Novo').first()
        context['leads_novo'] = Lead.objects.filter(pipeline=pipeline, stage=stage_novo).count() if stage_novo else 0

        # série dos últimos 7 dias para o gráfico de envios/dia
        dias = [hoje - timezone.timedelta(days=i) for i in range(6, -1, -1)]
        agregados = {
            row['data']: row['total']
            for row in DailyLimit.objects.filter(instance__owner=user, data__gte=dias[0])
            .values('data')
            .annotate(total=Sum('enviadas'))
        }
        context['grafico_labels'] = json.dumps([d.strftime('%d/%m') for d in dias])
        context['grafico_valores'] = json.dumps([agregados.get(d, 0) for d in dias])

        context['alertas'] = self._alertas(user, instancias)
        return context

    def _alertas(self, user, instancias):
        from antiblock.models import BlockEvent
        from instances.models import Instance

        alertas = []
        for instance in instancias:
            if not instance.ativo:
                alertas.append(f'Instância "{instance.nome}" está pausada.')
            elif instance.status != Instance.STATUS_CONECTADO:
                alertas.append(f'Instância "{instance.nome}" está {instance.get_status_display().lower()}.')

        recentes = BlockEvent.objects.filter(instance__owner=user, pausou_instancia=True).order_by('-created_at')[:3]
        for evento in recentes:
            alertas.append(f'"{evento.instance.nome}" foi pausada automaticamente: {evento.get_motivo_display()}.')
        return alertas


def healthz(request):
    """Healthcheck (Sprint 19): banco, broker do Celery e Evolution API."""
    from django.db import connections
    from django.http import JsonResponse

    status = {}
    ok = True

    try:
        connections['default'].cursor().execute('SELECT 1')
        status['database'] = 'ok'
    except Exception as exc:  # noqa: BLE001
        status['database'] = f'erro: {exc}'
        ok = False

    try:
        from core.celery import app as celery_app

        with celery_app.connection_for_write() as conn:
            conn.ensure_connection(max_retries=1, timeout=2)
        status['broker'] = 'ok'
    except Exception as exc:  # noqa: BLE001
        status['broker'] = f'erro: {exc}'
        ok = False

    try:
        from django.conf import settings as dj_settings

        import requests

        r = requests.get(f'{dj_settings.EVOLUTION_BASE_URL}/', timeout=3)
        status['evolution'] = 'ok' if r.status_code < 500 else f'status {r.status_code}'
    except Exception as exc:  # noqa: BLE001
        status['evolution'] = f'indisponível: {exc}'
        # a Evolution fora do ar não derruba o healthcheck do próprio Sparzap
        # (o app continua funcional para tudo que não depende dela na hora)

    return JsonResponse({'status': 'ok' if ok else 'degraded', 'checks': status}, status=200 if ok else 503)


class ComingSoonView(LoginRequiredMixin, TemplateView):
    """Placeholder de módulo ainda não implementado — ver PRD.md secao 13."""

    template_name = 'components/coming_soon.html'
    titulo = 'Em construção'
    sprint = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = self.titulo
        context['sprint'] = self.sprint
        return context
