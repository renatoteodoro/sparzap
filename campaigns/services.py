import logging

from django.utils import timezone

from antiblock.models import BlockEvent
from antiblock.services import can_send
from scripts.models import ScriptRun
from scripts.services import execute_step, first_step

from .models import Campaign, CampaignContact, DeliveryLog

logger = logging.getLogger('sparzap')

RETRY_BACKOFF_S = {
    BlockEvent.MOTIVO_LIMITE_DIARIO: 3600,
    BlockEvent.MOTIVO_FORA_JANELA: 1800,
}


def build_audience(campaign):
    """Materializa CampaignContact a partir do público (avulsos + membros dos grupos), com opt-out e anti-dup."""
    origem_grupo_por_contato = {}
    for group in campaign.grupos.all():
        for membro in group.membros.select_related('contact'):
            if not membro.contact.opt_out:
                origem_grupo_por_contato.setdefault(membro.contact, group)

    contatos = set(campaign.contatos_avulsos.filter(opt_out=False)) | set(origem_grupo_por_contato)

    contatos = _aplicar_filtro_publico(campaign, contatos)
    contatos = _aplicar_antiduplicacao(campaign, contatos)

    # Uma query para saber quem já está na campanha e um INSERT em lote para o
    # resto. Com `get_or_create` num loop, um grupo real de 778 membros custava
    # ~1.560 queries em sequência e o gunicorn abortava a request no timeout de
    # 30s. `ignore_conflicts` cobre a corrida de dois disparos simultâneos —
    # `uniq_campaign_contact` garante que nada duplica.
    ja_na_campanha = set(
        CampaignContact.objects.filter(campaign=campaign).values_list('contact_id', flat=True)
    )
    novos = [
        CampaignContact(
            campaign=campaign,
            contact=contact,
            origem_grupo=origem_grupo_por_contato.get(contact),
        )
        for contact in contatos
        if contact.id not in ja_na_campanha
    ]
    CampaignContact.objects.bulk_create(novos, ignore_conflicts=True)
    return len(novos)


def _aplicar_filtro_publico(campaign, contatos):
    if campaign.filtro_publico != Campaign.FILTRO_NAO_RESPONDEU:
        return contatos

    ja_respondeu_ids = set(
        CampaignContact.objects.filter(
            campaign__owner=campaign.owner,
            status=CampaignContact.STATUS_RESPONDIDA,
        ).values_list('contact_id', flat=True)
    )
    return {c for c in contatos if c.id not in ja_respondeu_ids}


def _aplicar_antiduplicacao(campaign, contatos):
    if not campaign.antiduplicacao_dias:
        return contatos

    desde = timezone.now() - timezone.timedelta(days=campaign.antiduplicacao_dias)
    ja_recebeu_recentemente_ids = set(
        CampaignContact.objects.filter(
            campaign__nome=campaign.nome,
            campaign__owner=campaign.owner,
            status__in=[CampaignContact.STATUS_ENVIADA, CampaignContact.STATUS_RESPONDIDA],
            enviado_em__gte=desde,
        )
        .exclude(campaign=campaign)
        .values_list('contact_id', flat=True)
    )
    return {c for c in contatos if c.id not in ja_recebeu_recentemente_ids}


def audience_preview_count(campaign):
    contatos = set(campaign.contatos_avulsos.filter(opt_out=False))
    for group in campaign.grupos.all():
        contatos |= {m.contact for m in group.membros.select_related('contact') if not m.contact.opt_out}
    contatos = _aplicar_filtro_publico(campaign, contatos)
    contatos = _aplicar_antiduplicacao(campaign, contatos)
    return len(contatos)


# --- Ciclo de vida da campanha ------------------------------------------


def start_campaign(campaign):
    if campaign.remover_admin_antes:
        from contacts.services import demote_self_for_campaign, refresh_group_admins_for_campaign

        # ORDEM IMPORTA: revalidar os admins ANTES de montar o público, senão
        # o público sai com os vínculos velhos e um admin recém-promovido
        # receberia o disparo.
        refresh_group_admins_for_campaign(campaign)
        demote_self_for_campaign(campaign)

    build_audience(campaign)
    campaign.status = Campaign.STATUS_EM_ANDAMENTO
    campaign.save(update_fields=['status', 'updated_at'])

    from .tasks import dispatch_campaign

    dispatch_campaign.delay(campaign.id)


def pause_campaign(campaign):
    campaign.status = Campaign.STATUS_PAUSADA
    campaign.save(update_fields=['status', 'updated_at'])


def resume_campaign(campaign):
    campaign.status = Campaign.STATUS_EM_ANDAMENTO
    campaign.save(update_fields=['status', 'updated_at'])

    from .tasks import dispatch_campaign

    dispatch_campaign.delay(campaign.id)


def cancel_campaign(campaign):
    campaign.status = Campaign.STATUS_CANCELADA
    campaign.save(update_fields=['status', 'updated_at'])


# --- Execução por contato ------------------------------------------------


def process_campaign_contact(campaign_contact):
    campaign = campaign_contact.campaign
    if campaign.status != Campaign.STATUS_EM_ANDAMENTO:
        return 'campanha_nao_ativa'

    permitido, motivo, detalhe = can_send(campaign.instance)
    if not permitido:
        if motivo in RETRY_BACKOFF_S:
            from django.conf import settings

            if settings.CELERY_TASK_ALWAYS_EAGER:
                # Em modo eager (dev sem broker real), apply_async(countdown=...)
                # roda NA HORA e de forma sincrona -- reagendar aqui recursaria
                # infinitamente enquanto o motivo do bloqueio nao mudar (ex.:
                # fora da janela de operacao a noite inteira), derrubando o
                # processo com RecursionError. Sem Celery real nao ha como
                # "esperar" de verdade, entao so deixamos pendente: o proximo
                # `dispatch_campaign` (manual ou de um Celery real em produção)
                # tenta de novo.
                return 'aguardando_condicao'

            from .tasks import send_campaign_contact

            send_campaign_contact.apply_async(args=[campaign_contact.id], countdown=RETRY_BACKOFF_S[motivo])
            return 'reagendado'

        campaign_contact.status = CampaignContact.STATUS_FALHA
        campaign_contact.erro = f'{motivo}: {detalhe}'
        campaign_contact.save(update_fields=['status', 'erro', 'updated_at'])
        return 'falha'

    contexto_extra = {'grupo': campaign_contact.origem_grupo.nome} if campaign_contact.origem_grupo_id else {}
    run = ScriptRun.objects.create(
        script=campaign.script,
        contact=campaign_contact.contact,
        instance=campaign.instance,
        passo_atual=first_step(campaign.script),
        origem=ScriptRun.ORIGEM_CAMPANHA,
        contexto_extra=contexto_extra,
    )
    campaign_contact.script_run = run
    campaign_contact.save(update_fields=['script_run', 'updated_at'])

    execute_step(run)
    run.refresh_from_db()

    if run.status == ScriptRun.STATUS_ERRO:
        campaign_contact.status = CampaignContact.STATUS_FALHA
        campaign_contact.erro = run.erro[:255]
    else:
        campaign_contact.status = CampaignContact.STATUS_ENVIADA
        campaign_contact.enviado_em = timezone.now()
        if run.ultimo_message_id:
            DeliveryLog.objects.create(
                campaign_contact=campaign_contact,
                status=DeliveryLog.STATUS_ENVIADA,
                message_id=run.ultimo_message_id,
            )
    campaign_contact.save(update_fields=['status', 'erro', 'enviado_em', 'updated_at'])
    return campaign_contact.status


# --- Chamado pelo webhook (messages.update) -------------------------------


def mark_responded(contact):
    """Marca como respondidos os CampaignContact 'enviada' — usado no filtro 'não respondeu' (RF-43)."""
    agora = timezone.now()
    return CampaignContact.objects.filter(
        contact=contact,
        status=CampaignContact.STATUS_ENVIADA,
    ).update(status=CampaignContact.STATUS_RESPONDIDA, respondido_em=agora, updated_at=agora)


def update_delivery_status(message_id, status):
    if not message_id or not status:
        return

    log = DeliveryLog.objects.filter(message_id=message_id).first()
    if log is None:
        return  # nada a atualizar; pode ser mensagem fora do fluxo de campanha

    DeliveryLog.objects.create(campaign_contact=log.campaign_contact, status=status, message_id=message_id)
