"""
Alertas operacionais (Sprint 19). Em vez de tentar notificar via WhatsApp
usando o próprio Sparzap (frágil: se a única instância for justamente a que
está com problema, não há como avisar por ela), os alertas vão para o log
estruturado (sempre) e, opcionalmente, para um webhook externo genérico
(Slack/Discord/etc, configurável via ALERT_WEBHOOK_URL) — mais simples e
mais confiável do que depender do próprio canal que pode estar quebrado.
"""

import logging

logger = logging.getLogger('sparzap.alerts')


def notify(evento, detalhe='', nivel='warning', **contexto):
    log_fn = getattr(logger, nivel, logger.warning)
    log_fn(f'alerta evento={evento} detalhe={detalhe}', extra={'evento': evento, **contexto})

    from django.conf import settings

    webhook_url = getattr(settings, 'ALERT_WEBHOOK_URL', '')
    if not webhook_url:
        return

    try:
        import requests

        requests.post(webhook_url, json={'evento': evento, 'detalhe': detalhe, 'nivel': nivel, **contexto}, timeout=3)
    except Exception:  # noqa: BLE001 — alerta nunca pode derrubar o fluxo que o disparou
        logger.exception('falha ao enviar alerta para ALERT_WEBHOOK_URL')
