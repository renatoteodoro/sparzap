import logging

from django.utils import timezone

from .models import ScriptRun, ScriptStep

logger = logging.getLogger('sparzap')


def get_step_by_ordem(script, ordem):
    return script.steps.filter(ordem=ordem).first()


def first_step(script):
    return script.steps.order_by('ordem').first()


def next_step(step):
    if step is None:
        return None
    return get_step_by_ordem(step.script, step.ordem + 1)


# --- Início de uma execução -------------------------------------------------


def start_run(script, contact, instance, origem=ScriptRun.ORIGEM_TESTE):
    run = ScriptRun.objects.create(
        script=script,
        contact=contact,
        instance=instance,
        passo_atual=first_step(script),
        origem=origem,
    )
    execute_step(run)
    return run


def run_test(script, contact, instance):
    return start_run(script, contact, instance, origem=ScriptRun.ORIGEM_TESTE)


# --- Motor de execução -------------------------------------------------------


def execute_step(run):
    step = run.passo_atual
    if step is None:
        _finish(run, ScriptRun.STATUS_CONCLUIDO)
        return

    try:
        if step.tipo == ScriptStep.TIPO_MENSAGEM:
            _send_step_message(run, step)
            _advance(run)
        elif step.tipo == ScriptStep.TIPO_DELAY:
            from .tasks import continue_after_delay

            continue_after_delay.apply_async(args=[run.id], countdown=step.delay_s or 0)
        elif step.tipo == ScriptStep.TIPO_AGUARDAR_RESPOSTA:
            run.status = ScriptRun.STATUS_AGUARDANDO
            run.aguardando_desde = timezone.now()
            run.save(update_fields=['status', 'aguardando_desde', 'updated_at'])

            from .tasks import check_timeout

            check_timeout.apply_async(args=[run.id, step.id], countdown=(step.timeout_h or 48) * 3600)
        elif step.tipo == ScriptStep.TIPO_CONDICAO:
            # so deveria ser alcançado via resume_waiting_steps (que já resolve o alvo);
            # se chegou aqui organicamente (sem passar por aguardar_resposta), segue em frente.
            _advance(run)
        elif step.tipo == ScriptStep.TIPO_MUDAR_ETAPA:
            _apply_mudar_etapa(run, step)
            _advance(run)
    except Exception as exc:  # noqa: BLE001 — nunca deixa o worker cair; registra e para o run
        logger.exception('script_run_erro run=%s step=%s', run.id, step.id)
        run.erro = str(exc)[:2000]
        _finish(run, ScriptRun.STATUS_ERRO)


def _advance(run):
    proximo = next_step(run.passo_atual)
    run.passo_atual = proximo
    run.status = ScriptRun.STATUS_EM_ANDAMENTO if proximo else ScriptRun.STATUS_CONCLUIDO
    run.save(update_fields=['passo_atual', 'status', 'updated_at'])
    if proximo:
        execute_step(run)


def _finish(run, status):
    run.status = status
    run.save(update_fields=['status', 'erro', 'updated_at'])


def _send_step_message(run, step):
    if step.message is None:
        return

    from library.services import render_message

    contexto = {'nome': run.contact.nome, **run.contexto_extra}
    texto = render_message(step.message, contexto)

    from antiblock import services as antiblock_services  # Sprint 7

    resultado = antiblock_services.dispatch(run.instance, run.contact.numero_e164, texto)

    message_id = (resultado or {}).get('key', {}).get('id', '')
    if message_id:
        run.ultimo_message_id = message_id
        run.save(update_fields=['ultimo_message_id', 'updated_at'])

    try:
        from crm import services as crm_services  # Sprint 11

        crm_services.log_outgoing_message(run.contact, texto)
    except Exception:  # noqa: BLE001 — historico de CRM nunca deve travar o envio
        logger.exception('script_log_outgoing_erro run=%s', run.id)


def _apply_mudar_etapa(run, step):
    if not step.etapa_destino:
        return

    from crm import services as crm_services  # Sprint 11

    crm_services.move_stage_by_name(run.contact, step.etapa_destino)


# --- Retomada por resposta (chamada pelo webhook) ---------------------------


def resume_waiting_steps(contact, texto):
    runs = ScriptRun.objects.filter(contact=contact, status=ScriptRun.STATUS_AGUARDANDO)
    for run in runs:
        _resume_run(run, texto)


def _resume_run(run, texto):
    step_aguardando = run.passo_atual
    candidato = next_step(step_aguardando)
    alvo = _resolve_condicao(run.script, candidato, texto)

    run.passo_atual = alvo
    run.status = ScriptRun.STATUS_EM_ANDAMENTO if alvo else ScriptRun.STATUS_CONCLUIDO
    run.save(update_fields=['passo_atual', 'status', 'updated_at'])
    if alvo:
        execute_step(run)


def _resolve_condicao(script, step, texto):
    """Se `step` for do tipo condição, resolve o alvo comparando `texto`; senão retorna o próprio `step`."""
    if step is None or step.tipo != ScriptStep.TIPO_CONDICAO:
        return step

    match = bool(step.condicao_contem) and step.condicao_contem.lower() in (texto or '').lower()
    if match and step.proximo_passo:
        return step.proximo_passo
    return next_step(step)


def handle_timeout(run_id, step_id):
    """Executado pelo Celery Beat/task se o timeout de `aguardar_resposta` expirar sem resposta (RF-31)."""
    run = ScriptRun.objects.filter(id=run_id).select_related('passo_atual').first()
    if run is None or run.status != ScriptRun.STATUS_AGUARDANDO or run.passo_atual_id != step_id:
        return  # já foi retomado por uma resposta real, ou o run não existe mais
    _resume_run(run, texto='')
