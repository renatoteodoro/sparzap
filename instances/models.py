import datetime

from django.conf import settings
from django.db import models

from core.models import BaseModel


class Instance(BaseModel):
    STATUS_DESCONECTADO = 'desconectado'
    STATUS_AGUARDANDO_QR = 'aguardando_qr'
    STATUS_CONECTADO = 'conectado'
    STATUS_BANIDO = 'banido'
    STATUS_CHOICES = [
        (STATUS_DESCONECTADO, 'Desconectado'),
        (STATUS_AGUARDANDO_QR, 'Aguardando QR'),
        (STATUS_CONECTADO, 'Conectado'),
        (STATUS_BANIDO, 'Banido'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='instances')
    nome = models.CharField('nome', max_length=100)
    evolution_instance_name = models.SlugField('nome na Evolution', max_length=100, unique=True)
    numero = models.CharField('número', max_length=20, blank=True)
    status = models.CharField('status', max_length=20, choices=STATUS_CHOICES, default=STATUS_DESCONECTADO)
    limite_diario = models.PositiveIntegerField('limite diário de envios', default=30)
    janela_inicio = models.TimeField('início da janela de envio', default=datetime.time(8, 0))
    janela_fim = models.TimeField('fim da janela de envio', default=datetime.time(21, 0))
    ativo = models.BooleanField('ativo', default=True)
    ultimo_status_em = models.DateTimeField('último status em', null=True, blank=True)

    class Meta:
        verbose_name = 'instância'
        verbose_name_plural = 'instâncias'
        ordering = ['-created_at']

    def __str__(self):
        return self.nome

    @property
    def pode_receber_disparo(self):
        return self.ativo and self.status == self.STATUS_CONECTADO


class InstanceEvent(BaseModel):
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='eventos')
    status_anterior = models.CharField(max_length=20, blank=True)
    status_novo = models.CharField(max_length=20)
    detalhe = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'evento de instância'
        verbose_name_plural = 'eventos de instância'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.instance.nome}: {self.status_anterior} -> {self.status_novo}'
