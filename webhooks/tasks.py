from celery import shared_task


@shared_task
def process_webhook_event(event_id):
    from .models import WebhookEvent
    from .services import process_event

    try:
        event = WebhookEvent.objects.select_related('instance').get(id=event_id)
    except WebhookEvent.DoesNotExist:
        return
    process_event(event)


@shared_task
def reconcile_missed_webhooks():
    """
    Reconciliação periódica: como não há um endpoint documentado da Evolution
    para listar conversas recentes de forma confiável entre versões, esta
    task hoje reprocessa eventos que ficaram com `processado=False` (falha
    transitória) e reconsulta o status das instâncias. Poll ativo de
    conversas na Evolution fica para revisão quando a instância real da VPS
    estiver acessível (ver docs/evolution.md).
    """
    from instances.tasks import refresh_all_instances_status

    from .models import WebhookEvent

    pendentes = WebhookEvent.objects.filter(processado=False)
    reprocessados = 0
    for event in pendentes.select_related('instance')[:200]:
        process_webhook_event.delay(event.id)
        reprocessados += 1

    refresh_all_instances_status.delay()
    return reprocessados


DIAS_RETENCAO_WEBHOOK_EVENT = 30


@shared_task
def purge_old_webhook_events():
    """Expurgo (Sprint 19, 19.3.1): remove WebhookEvent processados com mais de N dias."""
    from django.utils import timezone

    from .models import WebhookEvent

    limite = timezone.now() - timezone.timedelta(days=DIAS_RETENCAO_WEBHOOK_EVENT)
    apagados, _ = WebhookEvent.objects.filter(processado=True, created_at__lt=limite).delete()
    return apagados
