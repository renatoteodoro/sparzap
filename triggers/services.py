import logging

from django.utils import timezone

from .models import ScheduledMsg, Trigger, TriggerLog

logger = logging.getLogger('sparzap')


def _normaliza(texto):
    """Minúsculas e sem acento — mesma regra usada nas condições de roteiro."""
    from core.text import normalizar

    return normalizar(texto)


def _casa_palavras(trigger, texto_normalizado):
    palavras = trigger.lista_palavras()
    if not palavras:
        return False
    if trigger.modo == Trigger.MODO_E:
        return all(p in texto_normalizado for p in palavras)
    return any(p in texto_normalizado for p in palavras)


def _dentro_do_escopo(trigger, contact):
    if trigger.contato_id and trigger.contato_id != contact.id:
        return False
    # Escopo por grupo nao e' verificado aqui: o payload de mensagens.upsert
    # de conversas privadas nao carrega o grupo de origem, e o parser atual
    # de webhooks (Sprint 3) so trata remoteJid como numero de contato —
    # gatilhos com `grupo` definido nunca casam ate essa lacuna ser fechada.
    if trigger.grupo_id:
        return False
    return True


def _ja_respondeu_recentemente(trigger, contact):
    if not trigger.limite_repeticao_minutos:
        return False
    desde = timezone.now() - timezone.timedelta(minutes=trigger.limite_repeticao_minutos)
    return TriggerLog.objects.filter(trigger=trigger, contact=contact, created_at__gte=desde).exists()


def match_triggers(instance, contact, texto):
    """Retorna o primeiro Trigger ativo (em ordem de prioridade) que casa com o texto, ou None."""
    texto_normalizado = _normaliza(texto)
    candidatos = Trigger.objects.filter(instance=instance, ativo=True).order_by('prioridade', 'id')
    for trigger in candidatos:
        if not _dentro_do_escopo(trigger, contact):
            continue
        if not _casa_palavras(trigger, texto_normalizado):
            continue
        if _ja_respondeu_recentemente(trigger, contact):
            continue
        return trigger
    return None


def evaluate_triggers(instance, contact, texto):
    trigger = match_triggers(instance, contact, texto)
    if trigger is None:
        return None

    acoes = _executar_acoes(instance, contact, trigger)
    TriggerLog.objects.create(
        trigger=trigger,
        contact=contact,
        mensagem_recebida=texto[:2000],
        acoes_executadas=','.join(acoes),
    )
    return trigger


def _executar_acoes(instance, contact, trigger):
    acoes = []

    if trigger.resposta_id:
        try:
            from antiblock.services import dispatch
            from library.services import render_message

            texto_resposta = render_message(trigger.resposta, {'nome': contact.nome})
            dispatch(instance, contact.numero_e164, texto_resposta)
            acoes.append('responder')
        except Exception:  # noqa: BLE001 — gatilho nunca deve derrubar o processamento do webhook
            logger.exception('trigger_resposta_erro trigger=%s contact=%s', trigger.id, contact.id)

    if trigger.etiqueta_nome:
        from contacts.models import Tag

        tag, _ = Tag.objects.get_or_create(owner=contact.owner, nome=trigger.etiqueta_nome)
        contact.tags.add(tag)
        acoes.append('etiquetar')

    if trigger.etapa_destino:
        try:
            from crm import services as crm_services  # Sprint 11

            crm_services.move_stage_by_name(contact, trigger.etapa_destino)
            acoes.append('mudar_etapa')
        except Exception:  # noqa: BLE001
            logger.exception('trigger_mudar_etapa_erro trigger=%s contact=%s', trigger.id, contact.id)

    if trigger.followup_mensagem_id and trigger.followup_apos_horas:
        data_hora = timezone.now() + timezone.timedelta(hours=trigger.followup_apos_horas)
        schedule_message(contact, instance, trigger.followup_mensagem, data_hora, origem=ScheduledMsg.ORIGEM_GATILHO)
        acoes.append('agendar_followup')

    return acoes


# --- Follow-up individual (RF-53) -------------------------------------------


def schedule_message(contact, instance, message, data_hora, origem=ScheduledMsg.ORIGEM_MANUAL):
    return ScheduledMsg.objects.create(
        contact=contact,
        instance=instance,
        message=message,
        data_hora=data_hora,
        origem=origem,
    )


def cancel_scheduled_message(scheduled_msg):
    scheduled_msg.status = ScheduledMsg.STATUS_CANCELADA
    scheduled_msg.save(update_fields=['status', 'updated_at'])


def reschedule_message(scheduled_msg, nova_data_hora):
    scheduled_msg.data_hora = nova_data_hora
    scheduled_msg.status = ScheduledMsg.STATUS_PENDENTE
    scheduled_msg.save(update_fields=['data_hora', 'status', 'updated_at'])
    return scheduled_msg


def dispatch_due_scheduled_messages():
    """Roda periodicamente (Celery Beat): envia toda ScheduledMsg pendente cuja data_hora já passou."""
    from antiblock.services import AntiBlockBlocked, dispatch
    from library.services import render_message

    pendentes = ScheduledMsg.objects.filter(status=ScheduledMsg.STATUS_PENDENTE, data_hora__lte=timezone.now())
    enviadas = 0
    for agendada in pendentes.select_related('contact', 'instance', 'message'):
        texto = render_message(agendada.message, {'nome': agendada.contact.nome})
        try:
            dispatch(agendada.instance, agendada.contact.numero_e164, texto)
            agendada.status = ScheduledMsg.STATUS_ENVIADA
        except AntiBlockBlocked:
            continue  # tenta de novo na proxima execucao periodica
        except Exception as exc:  # noqa: BLE001
            logger.exception('scheduled_msg_erro id=%s', agendada.id)
            agendada.status = ScheduledMsg.STATUS_FALHA
            agendada.erro = str(exc)[:255]
        agendada.save(update_fields=['status', 'erro', 'updated_at'])
        enviadas += 1
    return enviadas
