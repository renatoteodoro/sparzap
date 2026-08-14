import logging

from celery import shared_task

logger = logging.getLogger('sparzap')


@shared_task
def dispatch_due_scheduled_messages():
    from .services import dispatch_due_scheduled_messages as _dispatch

    total = _dispatch()
    logger.info('dispatch_due_scheduled_messages total=%s', total)
    return total
