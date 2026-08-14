import logging

from django.conf import settings
from django.utils import timezone

from .evolution import EVOLUTION_WEBHOOK_EVENTS, EvolutionClient, EvolutionError
from .models import Instance, InstanceEvent

logger = logging.getLogger('sparzap')


def _client():
    return EvolutionClient()


def provision_instance(owner, nome, evolution_instance_name, limite_diario=30):
    """Cria a instância no Sparzap e na Evolution, e registra o webhook."""
    instance = Instance.objects.create(
        owner=owner,
        nome=nome,
        evolution_instance_name=evolution_instance_name,
        limite_diario=limite_diario,
        status=Instance.STATUS_DESCONECTADO,
    )

    client = _client()
    try:
        client.create_instance(instance.evolution_instance_name)
        webhook_url = (
            f'{settings.EVOLUTION_WEBHOOK_BASE_URL}/webhooks/evolution/'
            f'{instance.evolution_instance_name}/?token={settings.EVOLUTION_WEBHOOK_SECRET}'
        )
        client.set_webhook(instance.evolution_instance_name, webhook_url, EVOLUTION_WEBHOOK_EVENTS)
    except EvolutionError as exc:
        logger.warning('provision_instance_evolution_error instance=%s error=%s', instance.evolution_instance_name, exc)

    return instance


def get_qrcode(instance):
    """Retorna o payload de conexão (contém o QR code em base64) da Evolution."""
    client = _client()
    data = client.connect(instance.evolution_instance_name)
    set_status(instance, Instance.STATUS_AGUARDANDO_QR, detalhe='QR solicitado')
    return data


def set_numero(instance, numero):
    if numero and instance.numero != numero:
        instance.numero = numero
        instance.save(update_fields=['numero', 'updated_at'])
    return instance


def set_status(instance, novo_status, detalhe=''):
    if instance.status == novo_status:
        return instance

    InstanceEvent.objects.create(
        instance=instance,
        status_anterior=instance.status,
        status_novo=novo_status,
        detalhe=detalhe,
    )
    instance.status = novo_status
    instance.ultimo_status_em = timezone.now()
    instance.save(update_fields=['status', 'ultimo_status_em', 'updated_at'])

    if novo_status in (Instance.STATUS_DESCONECTADO, Instance.STATUS_BANIDO):
        from core.alerts import notify

        notify(
            'instancia_desconectada',
            detalhe=f'Instância "{instance.nome}" mudou para {novo_status} ({detalhe}).',
            nivel='warning',
            instance_id=instance.id,
        )

    return instance


def refresh_status(instance):
    client = _client()
    try:
        data = client.connection_state(instance.evolution_instance_name)
    except EvolutionError as exc:
        logger.warning('refresh_status_error instance=%s error=%s', instance.evolution_instance_name, exc)
        return instance

    estado = (data.get('instance') or {}).get('state') or data.get('state')
    mapa = {
        'open': Instance.STATUS_CONECTADO,
        'connecting': Instance.STATUS_AGUARDANDO_QR,
        'close': Instance.STATUS_DESCONECTADO,
    }
    novo_status = mapa.get(estado, instance.status)
    return set_status(instance, novo_status, detalhe=f'refresh_status: {estado}')


def send_test_message(instance, numero, texto='Teste de conexão do Sparzap ✅'):
    client = _client()
    return client.send_text(instance.evolution_instance_name, numero, texto)


def deactivate_instance(instance):
    instance.ativo = False
    instance.save(update_fields=['ativo', 'updated_at'])
    return instance
