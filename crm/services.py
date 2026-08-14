import logging

from django.utils import timezone

from .models import ConversationMessage, Lead, LeadNote, Pipeline, Stage

logger = logging.getLogger('sparzap')

ETAPAS_PADRAO = ['Novo', 'Contatado', 'Respondeu', 'Interessado', 'Vendido', 'Perdido']
ETAPAS_FINAIS = {'Vendido', 'Perdido'}


def get_or_create_default_pipeline(owner):
    pipeline, created = Pipeline.objects.get_or_create(owner=owner, nome='Padrão')
    if created or not pipeline.stages.exists():
        for i, nome in enumerate(ETAPAS_PADRAO):
            Stage.objects.get_or_create(
                pipeline=pipeline,
                nome=nome,
                defaults={'ordem': i, 'e_final': nome in ETAPAS_FINAIS},
            )
    return pipeline


def get_or_create_lead(contact, origem=''):
    pipeline = get_or_create_default_pipeline(contact.owner)
    primeira_etapa = pipeline.stages.order_by('ordem').first()
    lead, created = Lead.objects.get_or_create(
        contact=contact,
        pipeline=pipeline,
        defaults={'stage': primeira_etapa, 'origem': origem},
    )
    return lead


def move_stage(lead, stage, motivo=''):
    if lead.stage_id == stage.id:
        return lead
    anterior = lead.stage.nome
    lead.stage = stage
    lead.entrou_na_etapa_em = timezone.now()
    lead.save(update_fields=['stage', 'entrou_na_etapa_em', 'updated_at'])
    LeadNote.objects.create(
        lead=lead,
        automatica=True,
        texto=f'Etapa alterada: {anterior} → {stage.nome}' + (f' ({motivo})' if motivo else ''),
    )
    return lead


def move_stage_by_name(contact, etapa_nome):
    """Usado por scripts.mudar_etapa e triggers.etapa_destino — move (ou cria) o lead para a etapa pelo nome."""
    lead = get_or_create_lead(contact)
    stage, _ = Stage.objects.get_or_create(
        pipeline=lead.pipeline,
        nome=etapa_nome,
        defaults={'ordem': lead.pipeline.stages.count()},
    )
    return move_stage(lead, stage, motivo='automático')


def log_incoming_message(contact, texto):
    lead = get_or_create_lead(contact)
    ConversationMessage.objects.create(lead=lead, direcao=ConversationMessage.DIRECAO_ENTRADA, conteudo=texto)

    # uma resposta espontanea do lead avança a etapa de "Novo" para "Respondeu"
    # (mas nunca regride uma etapa mais avançada, ex.: já Interessado/Vendido)
    if lead.stage.nome in ('Novo', 'Contatado'):
        respondeu = Stage.objects.filter(pipeline=lead.pipeline, nome='Respondeu').first()
        if respondeu:
            move_stage(lead, respondeu, motivo='respondeu por mensagem')
    return lead


def log_outgoing_message(contact, texto):
    lead = get_or_create_lead(contact)
    ConversationMessage.objects.create(lead=lead, direcao=ConversationMessage.DIRECAO_SAIDA, conteudo=texto)
    if lead.stage.nome == 'Novo':
        contatado = Stage.objects.filter(pipeline=lead.pipeline, nome='Contatado').first()
        if contatado:
            move_stage(lead, contatado, motivo='primeira mensagem enviada')
    return lead


def stage_conversion(pipeline):
    """Retorna [{'etapa': nome, 'total': n, 'percentual': p}] em relação ao total de leads do pipeline."""
    total = Lead.objects.filter(pipeline=pipeline).count()
    resultado = []
    for stage in pipeline.stages.order_by('ordem'):
        qtd = Lead.objects.filter(pipeline=pipeline, stage=stage).count()
        resultado.append(
            {
                'etapa': stage.nome,
                'total': qtd,
                'percentual': round(100 * qtd / total, 1) if total else 0,
            }
        )
    return resultado
