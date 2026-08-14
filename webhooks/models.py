from django.db import models

from core.models import BaseModel
from instances.models import Instance


class WebhookEvent(BaseModel):
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='webhook_events')
    evento = models.CharField('tipo do evento', max_length=50)
    message_id = models.CharField('id da mensagem (idempotência)', max_length=100, blank=True, db_index=True)
    payload = models.JSONField('payload bruto')
    processado = models.BooleanField('processado', default=False)
    erro = models.TextField('erro', blank=True)

    class Meta:
        verbose_name = 'evento de webhook'
        verbose_name_plural = 'eventos de webhook'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['instance', 'evento', 'processado']),
        ]

    def __str__(self):
        return f'{self.evento} @ {self.instance.nome} ({self.created_at:%d/%m %H:%M})'
