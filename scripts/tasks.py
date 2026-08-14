from celery import shared_task


@shared_task
def continue_after_delay(run_id):
    from .models import ScriptRun
    from .services import _advance

    run = ScriptRun.objects.filter(id=run_id).first()
    if run and run.status == ScriptRun.STATUS_EM_ANDAMENTO:
        _advance(run)


@shared_task
def check_timeout(run_id, step_id):
    from .services import handle_timeout

    handle_timeout(run_id, step_id)
