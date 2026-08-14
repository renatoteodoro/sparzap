import logging

from celery import shared_task

logger = logging.getLogger('sparzap')


@shared_task
def ping():
    """Task de diagnostico: confirma que worker/beat conseguem executar uma task."""
    logger.info('pong')
    return 'pong'


LIMIAR_FILA = 500  # tarefas pendentes acima disso -> alerta de acumulo anormal


@shared_task
def check_queue_size():
    """Roda periodicamente (Sprint 19, 19.2.4): alerta se a fila padrão do Celery acumular demais."""
    from django.conf import settings

    from .alerts import notify

    if settings.CELERY_TASK_ALWAYS_EAGER:
        # em modo eager nao ha fila de verdade (tasks rodam na hora) -- nada a medir
        return 0

    try:
        from core.celery import app as celery_app

        with celery_app.connection_for_read() as conn:
            tamanho = conn.default_channel.queue_declare(queue='celery', passive=True).message_count
    except Exception:  # noqa: BLE001
        logger.exception('check_queue_size_erro')
        return None

    if tamanho >= LIMIAR_FILA:
        notify(
            'fila_celery_acumulada',
            detalhe=f'{tamanho} tarefas pendentes na fila "celery" (limiar: {LIMIAR_FILA}).',
            nivel='error',
            tamanho_fila=tamanho,
        )
    return tamanho
