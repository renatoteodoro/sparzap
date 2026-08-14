import logging

from celery import shared_task

logger = logging.getLogger('sparzap')


@shared_task
def sync_groups_task(instance_id):
    """
    Sincroniza os grupos de uma instância fora do ciclo request/response.

    `fetchAllGroups` da Evolution leva ~90s numa conta real com dezenas de
    grupos (ver TIMEOUT_LENTO em instances/evolution.py). Isso não cabe num
    request HTTP: o gunicorn de produção mata o worker em 30s (default) e o
    Nginx devolve 504 em 60s. Por isso a view enfileira esta task em vez de
    chamar o service direto.
    """
    from instances.models import Instance

    from .services import sync_groups

    instance = Instance.objects.filter(id=instance_id).first()
    if instance is None:
        return 0

    grupos = sync_groups(instance)
    logger.info('sync_groups_task instance=%s grupos=%s', instance.evolution_instance_name, len(grupos))
    return len(grupos)


@shared_task
def extract_participants_task(group_id):
    """Extrai os participantes de um grupo — mesmo motivo de `sync_groups_task`."""
    from .models import Group
    from .services import extract_participants

    group = Group.objects.filter(id=group_id).select_related('instance').first()
    if group is None:
        return 0

    contatos = extract_participants(group)
    logger.info('extract_participants_task group=%s contatos=%s', group.jid, len(contatos))
    return len(contatos)
