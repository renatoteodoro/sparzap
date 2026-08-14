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

            from django.conf import settings

            if settings.CELERY_TASK_ALWAYS_EAGER:
                # Em modo eager (dev sem broker real), apply_async(countdown=...)
                # roda NA HORA e de forma sincrona -- agendar o timeout aqui faria
                # o run "expirar" no mesmo instante, pulando a espera de verdade
                # e disparando o proximo passo em seguida (as duas mensagens saem
                # juntas). Sem Celery real nao ha como agendar um timeout futuro;
                # quem retoma o run e' resume_waiting_steps, chamado pelo webhook
                # quando a resposta real chega.
                return

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
    """
    Se `step` for do tipo condição, resolve o alvo comparando `texto`; senão
    retorna o próprio `step`.

    A IA só é consultada quando TUDO abaixo vale — qualquer item que falte
    cai no matching por palavra-chave de sempre:

    - `script.usar_ia` ligado (interruptor geral — botão na tela do script);
    - `step.usar_ia` ligado, com `ia_config` configurada e ativa;
    - `condicao_ia_descricao` preenchida (sem critério a IA chuta);
    - `texto` não vazio (um timeout sem resposta chega aqui com `texto=''`;
      classificar o vazio pode desviar o run sem resposta real do contato).

    Se a IA responder com sucesso (True/False), o resultado dela decide o
    desvio, com a MESMA semântica do `condicao_contem`: casou → pula para
    `proximo_passo`; não casou → segue na ordem normal. Por isso a descrição
    tem que apontar na mesma direção do `condicao_contem` (ver o help_text
    dos dois campos) — descrevê-la ao contrário inverte o funil inteiro.

    `condicao_contem` aceita vários termos separados por vírgula e casa se
    QUALQUER um aparecer na resposta. A comparação ignora maiúsculas E
    acentos — quem responde pelo celular escreve "nao", "vc", "obrigado" sem
    acentuação, e uma condição que só reconhecesse "não" falharia com a
    maior parte das pessoas.
    """
    if step is None or step.tipo != ScriptStep.TIPO_CONDICAO:
        return step

    if (
        script.usar_ia
        and step.usar_ia
        and step.ia_config_id
        and step.ia_config.ativo
        and step.condicao_ia_descricao.strip()
        and (texto or '').strip()
    ):
        from ai.services import classificar  # Sprint 20: IA nos passos de condição

        resultado_ia = classificar(step.ia_config, step.condicao_ia_descricao, texto)
        if resultado_ia is not None:
            return step.proximo_passo if (resultado_ia and step.proximo_passo) else next_step(step)
        logger.warning('script_ia_fallback_keyword script=%s step=%s', script.id, step.id)

    from core.text import contem_algum, separar_termos

    if contem_algum(texto, separar_termos(step.condicao_contem)) and step.proximo_passo:
        return step.proximo_passo
    return next_step(step)


def explicar_erro(run):
    """
    Traduz o erro cru de um ScriptRun em algo que o usuário entenda e possa
    resolver. O texto guardado em `run.erro` vem de `AntiBlockBlocked` no
    formato 'motivo: detalhe' — sozinho ele não diz o que fazer.
    """
    from antiblock.models import BlockEvent

    erro = (run.erro or '').strip()
    if not erro:
        return 'motivo não registrado.'

    motivo, _, detalhe = erro.partition(':')
    motivo = motivo.strip()
    detalhe = detalhe.strip()
    instancia = run.instance

    if motivo == BlockEvent.MOTIVO_FORA_JANELA:
        agora = timezone.localtime().strftime('%H:%M')
        return (
            f'a instância "{instancia.nome}" só envia entre '
            f'{instancia.janela_inicio:%H:%M} e {instancia.janela_fim:%H:%M}, e agora são {agora}. '
            'Ajuste a janela na instância ou teste dentro desse horário.'
        )
    if motivo == BlockEvent.MOTIVO_LIMITE_DIARIO:
        return (
            f'o limite diário da instância "{instancia.nome}" já foi atingido ({detalhe}). '
            'Aguarde amanhã ou aumente o limite.'
        )
    if motivo == BlockEvent.MOTIVO_DESCONECTADO:
        return f'a instância "{instancia.nome}" não está pronta para enviar ({detalhe}). Reconecte o QR Code.'
    if motivo == BlockEvent.MOTIVO_RATE_LIMIT:
        return 'o WhatsApp recusou o envio por excesso de mensagens. Aguarde antes de tentar de novo.'
    return erro


def handle_timeout(run_id, step_id):
    """Executado pelo Celery Beat/task se o timeout de `aguardar_resposta` expirar sem resposta (RF-31)."""
    run = ScriptRun.objects.filter(id=run_id).select_related('passo_atual').first()
    if run is None or run.status != ScriptRun.STATUS_AGUARDANDO or run.passo_atual_id != step_id:
        return  # já foi retomado por uma resposta real, ou o run não existe mais
    _resume_run(run, texto='')
