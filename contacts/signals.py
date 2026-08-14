"""
Efeitos colaterais de apagar um Contact.

Primeiro (e único) uso de signals no projeto. A regra de negócio normalmente
mora em `services.py`, mas aqui ela precisa valer para **qualquer** caminho
de exclusão — a view genérica (`ContactDeleteView`), o `dedupe_contacts`
(que apaga o duplicado com queryset `.delete()`) e o Django Admin. Um
service só cobriria quem se lembrasse de chamá-lo.
"""

import logging

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Contact

logger = logging.getLogger('sparzap')


@receiver(pre_delete, sender=Contact)
def desativar_gatilhos_restritos_ao_contato(sender, instance, **kwargs):
    """
    `Trigger.contato` é SET_NULL. Sem isto, apagar o contato transformaria um
    gatilho restrito a UMA pessoa num gatilho **global**, que passaria a
    responder automaticamente para a base inteira — exatamente o oposto do
    que foi configurado, e um belo caminho para tomar bloqueio.

    Desativamos em vez de apagar: a configuração é preservada e o usuário
    pode reapontar o gatilho para outro contato e reativar.
    """
    from triggers.models import Trigger

    desativados = Trigger.objects.filter(contato=instance, ativo=True).update(ativo=False)
    if desativados:
        logger.info('gatilhos_desativados_por_exclusao_de_contato contact=%s total=%s', instance.pk, desativados)
