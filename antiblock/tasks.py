import logging

from celery import shared_task

logger = logging.getLogger('sparzap')


@shared_task
def advance_warmup_plans():
    from .services import advance_all_warmups

    total = advance_all_warmups()
    logger.info('advance_warmup_plans total=%s', total)
    return total
