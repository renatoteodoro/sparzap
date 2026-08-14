"""
Dispatcher de eventos da Evolution API. Alguns handlers dependem de apps
construídas em sprints posteriores (contacts, scripts, triggers, campaigns) —
à medida que cada uma existe, o handler correspondente é completado aqui.
"""

import logging

from instances import services as instances_services
from instances.models import Instance

logger = logging.getLogger('sparzap')

STATE_MAP = {
    'open': Instance.STATUS_CONECTADO,
    'connecting': Instance.STATUS_AGUARDANDO_QR,
    'close': Instance.STATUS_DESCONECTADO,
}


def extract_message_id(payload):
    data = payload.get('data') or {}
    key = data.get('key') or {}
    return key.get('id', '') or payload.get('id', '')


def process_event(event):
    """Processa um WebhookEvent persistido. Idempotente por message_id (ver receive_webhook)."""
    handler = _HANDLERS.get(event.evento)
    if handler is None:
        logger.info('webhook_event_sem_handler evento=%s instance=%s', event.evento, event.instance_id)
        event.processado = True
        event.save(update_fields=['processado', 'updated_at'])
        return

    try:
        handler(event)
        event.processado = True
        event.erro = ''
    except Exception as exc:  # noqa: BLE001 — nunca deixamos o worker cair por payload malformado
        logger.exception('webhook_event_erro evento=%s instance=%s', event.evento, event.instance_id)
        event.erro = str(exc)[:2000]
    event.save(update_fields=['processado', 'erro', 'updated_at'])


def _handle_connection_update(event):
    data = event.payload.get('data') or {}
    estado = data.get('state')
    novo_status = STATE_MAP.get(estado)
    if novo_status:
        instances_services.set_status(event.instance, novo_status, detalhe='webhook connection.update')

    # campo de numero conectado varia entre versoes da Evolution
    # (wuid/jid/user); tentamos os nomes mais comuns e ignoramos se ausente.
    numero_bruto = data.get('wuid') or data.get('jid') or data.get('user')
    if numero_bruto:
        from contacts.utils import normalize_br_number

        numero = normalize_br_number(numero_bruto)
        if numero:
            instances_services.set_numero(event.instance, numero)


def _handle_messages_upsert(event):
    data = event.payload.get('data') or {}
    key = data.get('key') or {}
    if key.get('fromMe'):
        logger.debug('webhook_messages_upsert_ignorado fromMe instance=%s', event.instance_id)
        return

    numero = (key.get('remoteJid') or '').split('@')[0]
    texto = (
        (data.get('message') or {}).get('conversation')
        or (data.get('message') or {}).get('extendedTextMessage', {}).get('text')
        or ''
    )

    # Sprint 4 (contacts): upsert do Contact a partir de `numero`.
    # Sprint 6 (scripts): retomar CampaignContact aguardando resposta.
    # Sprint 10 (triggers): avaliar gatilhos por palavra-chave.
    from contacts import services as contacts_services  # import tardio: quebra de ciclo entre apps

    contact = contacts_services.upsert_contact_from_webhook(event.instance.owner, numero)

    from crm import services as crm_services

    crm_services.log_incoming_message(contact, texto)

    from scripts import services as scripts_services

    scripts_services.resume_waiting_steps(contact, texto)

    from campaigns import services as campaigns_services  # Sprint 8

    campaigns_services.mark_responded(contact)

    from triggers import services as triggers_services

    triggers_services.evaluate_triggers(event.instance, contact, texto)


def _handle_messages_update(event):
    data = event.payload.get('data') or {}
    key = data.get('key') or {}
    message_id = key.get('id', '')
    status = data.get('update', {}).get('status') or data.get('status')

    from campaigns import services as campaigns_services

    campaigns_services.update_delivery_status(message_id, status)


def _handle_contacts_upsert(event):
    data = event.payload.get('data') or {}
    numero = (data.get('id') or '').split('@')[0]
    nome = data.get('pushName') or data.get('name') or ''
    if not numero:
        return

    from contacts import services as contacts_services

    contacts_services.upsert_contact_from_webhook(event.instance.owner, numero, nome=nome)


_HANDLERS = {
    'connection.update': _handle_connection_update,
    'messages.upsert': _handle_messages_upsert,
    'messages.update': _handle_messages_update,
    'contacts.upsert': _handle_contacts_upsert,
}
