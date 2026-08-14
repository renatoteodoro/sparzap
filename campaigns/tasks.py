import logging

from celery import shared_task

logger = logging.getLogger('sparzap')


@shared_task
def dispatch_campaign(campaign_id):
    from antiblock.services import next_delay_seconds

    from .models import Campaign, CampaignContact

    campaign = Campaign.objects.filter(id=campaign_id).select_related('instance').first()
    if campaign is None or campaign.status != Campaign.STATUS_EM_ANDAMENTO:
        return 0

    pendentes = CampaignContact.objects.filter(campaign=campaign, status=CampaignContact.STATUS_PENDENTE)
    cumulativo = 0
    agendados = 0
    for cc in pendentes:
        send_campaign_contact.apply_async(args=[cc.id], countdown=cumulativo)
        cumulativo += next_delay_seconds(campaign.instance)
        agendados += 1

    logger.info('dispatch_campaign campaign=%s agendados=%s', campaign_id, agendados)
    return agendados


@shared_task
def send_campaign_contact(campaign_contact_id):
    from .models import CampaignContact
    from .services import process_campaign_contact

    cc = CampaignContact.objects.filter(id=campaign_contact_id).select_related('campaign', 'contact').first()
    if cc is None or cc.status != CampaignContact.STATUS_PENDENTE:
        return None
    return process_campaign_contact(cc)


LIMIAR_TAXA_FALHA = 0.3  # 30% de falhas entre o ja processado dispara alerta
MINIMO_PROCESSADO_PARA_AVALIAR = 10


@shared_task
def check_failure_rates():
    """Roda periodicamente (Sprint 19, 19.2.3): alerta campanhas em andamento com taxa de falha alta."""
    from core.alerts import notify

    from .models import Campaign, CampaignContact

    alertadas = 0
    for campaign in Campaign.objects.filter(status=Campaign.STATUS_EM_ANDAMENTO):
        contatos = campaign.campaign_contacts.exclude(status=CampaignContact.STATUS_PENDENTE)
        total = contatos.count()
        if total < MINIMO_PROCESSADO_PARA_AVALIAR:
            continue

        falhas = contatos.filter(status=CampaignContact.STATUS_FALHA).count()
        taxa = falhas / total
        if taxa >= LIMIAR_TAXA_FALHA:
            notify(
                'campanha_taxa_falha_alta',
                detalhe=f'Campanha "{campaign.nome}": {falhas}/{total} falharam ({taxa:.0%}).',
                nivel='error',
                campaign_id=campaign.id,
            )
            alertadas += 1
    return alertadas
