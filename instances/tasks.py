import logging

from celery import shared_task

logger = logging.getLogger('sparzap')


@shared_task
def refresh_all_instances_status():
    """Consulta o status de todas as instâncias ativas na Evolution API (Celery Beat)."""
    from . import services
    from .models import Instance

    total = 0
    for instance in Instance.objects.filter(ativo=True):
        services.refresh_status(instance)
        total += 1
    logger.info('refresh_all_instances_status total=%s', total)
    return total
