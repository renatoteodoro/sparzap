import logging
import random

from django.db import transaction
from django.utils import timezone

from instances.evolution import EvolutionClient, EvolutionError, EvolutionRateLimited

from .models import BlockEvent, DailyLimit, RateSettings, WarmupActivity, WarmupPlan

logger = logging.getLogger('sparzap')

FALHAS_PARA_AUTO_PAUSA = 5
FATOR_MAXIMO = 5.0
FATOR_INCREMENTO = 1.5


class AntiBlockBlocked(Exception):
    """Levantada quando `dispatch` é chamado mas o AntiBlock não permite o envio agora."""

    def __init__(self, motivo, detalhe=''):
        self.motivo = motivo
        self.detalhe = detalhe
        super().__init__(f'{motivo}: {detalhe}' if detalhe else motivo)


def _rate_settings(instance):
    settings_obj, _ = RateSettings.objects.get_or_create(instance=instance)
    return settings_obj


def _today_limit(instance):
    limite, _ = DailyLimit.objects.get_or_create(instance=instance, data=timezone.localdate())
    return limite


def can_send(instance):
    """Retorna (permitido: bool, motivo: str|None, detalhe: str)."""
    if not instance.ativo:
        return False, BlockEvent.MOTIVO_DESCONECTADO, 'instância desativada/pausada'

    if instance.status != instance.STATUS_CONECTADO:
        return False, BlockEvent.MOTIVO_DESCONECTADO, f'status atual: {instance.status}'

    agora = timezone.localtime().time()
    dentro_da_janela = instance.janela_inicio <= agora <= instance.janela_fim
    if not dentro_da_janela:
        return False, BlockEvent.MOTIVO_FORA_JANELA, f'janela {instance.janela_inicio}–{instance.janela_fim}'

    limite = _today_limit(instance)
    if limite.enviadas >= instance.limite_diario:
        return False, BlockEvent.MOTIVO_LIMITE_DIARIO, f'{limite.enviadas}/{instance.limite_diario} hoje'

    return True, None, ''


def next_delay_seconds(instance):
    rate = _rate_settings(instance)
    base = random.randint(rate.intervalo_min_s, max(rate.intervalo_min_s, rate.intervalo_max_s))
    return round(base * rate.fator_escalonamento)


def register_success(instance):
    rate = _rate_settings(instance)
    if rate.falhas_consecutivas or rate.fator_escalonamento != 1.0:
        rate.falhas_consecutivas = 0
        rate.fator_escalonamento = 1.0
        rate.save(update_fields=['falhas_consecutivas', 'fator_escalonamento', 'updated_at'])


def register_failure(instance, motivo=BlockEvent.MOTIVO_FALHAS_CONSECUTIVAS, detalhe=''):
    rate = _rate_settings(instance)
    rate.falhas_consecutivas += 1
    rate.fator_escalonamento = min(FATOR_MAXIMO, rate.fator_escalonamento * FATOR_INCREMENTO)
    rate.save(update_fields=['falhas_consecutivas', 'fator_escalonamento', 'updated_at'])

    pausou = False
    if rate.falhas_consecutivas >= FALHAS_PARA_AUTO_PAUSA:
        from instances import services as instances_services

        instances_services.deactivate_instance(instance)
        pausou = True
        logger.warning('antiblock_auto_pausa instance=%s falhas=%s', instance.id, rate.falhas_consecutivas)

        from core.alerts import notify

        notify(
            'campanha_pausada_automaticamente',
            detalhe=f'Instância "{instance.nome}" pausada após {rate.falhas_consecutivas} falhas ({motivo}).',
            nivel='error',
            instance_id=instance.id,
        )

    BlockEvent.objects.create(instance=instance, motivo=motivo, detalhe=detalhe, pausou_instancia=pausou)
    return pausou


def increment_daily_count(instance):
    with transaction.atomic():
        limite = DailyLimit.objects.select_for_update().get_or_create(
            instance=instance,
            data=timezone.localdate(),
        )[0]
        limite.enviadas += 1
        limite.save(update_fields=['enviadas', 'updated_at'])
    return limite.enviadas


def dispatch(instance, numero, texto=None, tipo='texto', midia_url=None, caption=''):
    """
    Única porta de saída para a Evolution API. Nenhum envio deve chamar
    EvolutionClient diretamente fora daqui (RNF-04).
    """
    permitido, motivo, detalhe = can_send(instance)
    if not permitido:
        logger.info('antiblock_bloqueado instance=%s motivo=%s detalhe=%s', instance.id, motivo, detalhe)
        raise AntiBlockBlocked(motivo, detalhe)

    client = EvolutionClient()
    try:
        if tipo == 'texto':
            resultado = client.send_text(instance.evolution_instance_name, numero, texto)
        elif tipo == 'audio':
            resultado = client.send_audio(instance.evolution_instance_name, numero, midia_url)
        elif tipo == 'mention':
            # `numero` aqui e' o JID do grupo; mencao a todos os membros (RF F1/9.2.5)
            resultado = client.send_mention(instance.evolution_instance_name, numero, texto)
        else:
            resultado = client.send_media(
                instance.evolution_instance_name, numero, midia_url, media_type=tipo, caption=caption or texto or ''
            )
    except EvolutionRateLimited as exc:
        register_failure(instance, motivo=BlockEvent.MOTIVO_RATE_LIMIT, detalhe=str(exc)[:200])
        raise
    except EvolutionError as exc:
        register_failure(instance, motivo=BlockEvent.MOTIVO_FALHAS_CONSECUTIVAS, detalhe=str(exc)[:200])
        raise

    register_success(instance)
    increment_daily_count(instance)
    return resultado


# --- Aquecimento de número (RF-67 / Sprint 13) ------------------------------
#
# O aquecimento funciona ajustando `Instance.limite_diario` dia a dia — o
# controlador `can_send` já usa esse campo para bloquear envios acima do
# limite, então uma campanha grande é naturalmente barrada enquanto o plano
# está em andamento, sem precisar de uma checagem redundante em `campaigns`.

CURVA_PADRAO_INICIAL = 5


def _curva_do_dia(dia, dias_total, limite_final):
    """Progressão linear de CURVA_PADRAO_INICIAL (dia 1) até limite_final (último dia)."""
    if dias_total <= 1:
        return limite_final
    passo = (limite_final - CURVA_PADRAO_INICIAL) / (dias_total - 1)
    return max(1, round(CURVA_PADRAO_INICIAL + passo * (dia - 1)))


def start_warmup(instance, dias_total=14):
    plan = WarmupPlan.objects.create(
        instance=instance,
        inicio=timezone.localdate(),
        dias_total=dias_total,
        dia_atual=1,
        limite_final=instance.limite_diario,
    )
    _aplicar_dia(plan)
    return plan


def pause_warmup(plan):
    plan.status = WarmupPlan.STATUS_PAUSADO
    plan.save(update_fields=['status', 'updated_at'])


def resume_warmup(plan):
    plan.status = WarmupPlan.STATUS_EM_ANDAMENTO
    plan.save(update_fields=['status', 'updated_at'])


def _aplicar_dia(plan):
    limite_hoje = _curva_do_dia(plan.dia_atual, plan.dias_total, plan.limite_final)
    plan.instance.limite_diario = limite_hoje
    plan.instance.save(update_fields=['limite_diario', 'updated_at'])
    WarmupActivity.objects.create(plan=plan, dia=plan.dia_atual, limite_do_dia=limite_hoje)
    return limite_hoje


def advance_all_warmups():
    """Roda 1x/dia via Celery Beat: avança cada plano ativo para o próximo dia (ou conclui)."""
    avancados = 0
    for plan in WarmupPlan.objects.filter(status=WarmupPlan.STATUS_EM_ANDAMENTO).select_related('instance'):
        plan.dia_atual += 1
        if plan.dia_atual > plan.dias_total:
            plan.status = WarmupPlan.STATUS_CONCLUIDO
            plan.instance.limite_diario = plan.limite_final
            plan.instance.save(update_fields=['limite_diario', 'updated_at'])
            plan.save(update_fields=['status', 'dia_atual', 'updated_at'])
        else:
            plan.save(update_fields=['dia_atual', 'updated_at'])
            _aplicar_dia(plan)
        avancados += 1
    return avancados
