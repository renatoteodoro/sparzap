from django.conf import settings
from django.db import models

from contacts.models import Contact, Group
from core.models import BaseModel
from instances.models import Instance
from library.models import Message


class Trigger(BaseModel):
    MODO_OU = 'ou'
    MODO_E = 'e'
    MODO_CHOICES = [(MODO_OU, 'Qualquer palavra (OU)'), (MODO_E, 'Todas as palavras (E)')]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='triggers')
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='triggers')
    nome = models.CharField('nome', max_length=100)
    palavras_chave = models.CharField('palavras-chave (separadas por vírgula)', max_length=255)
    modo = models.CharField('modo', max_length=10, choices=MODO_CHOICES, default=MODO_OU)

    grupo = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggers',
        help_text='Restringe o gatilho a este grupo (opcional).',
    )
    contato = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggers',
        help_text='Restringe o gatilho a este contato (opcional).',
    )

    resposta = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    etiqueta_nome = models.CharField('nome da etiqueta a aplicar', max_length=50, blank=True)
    etapa_destino = models.CharField('etapa destino (crm)', max_length=100, blank=True)
    followup_mensagem = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='mensagem de follow-up',
        help_text='Se definida, agenda esta mensagem após o gatilho disparar.',
    )
    followup_apos_horas = models.PositiveIntegerField('agendar follow-up após (horas)', null=True, blank=True)

    prioridade = models.PositiveIntegerField('prioridade (menor = avaliado primeiro)', default=100)
    ativo = models.BooleanField('ativo', default=True)
    limite_repeticao_minutos = models.PositiveIntegerField('não repetir por (minutos)', default=60)

    class Meta:
        verbose_name = 'gatilho'
        verbose_name_plural = 'gatilhos'
        ordering = ['prioridade', 'nome']

    def __str__(self):
        return self.nome

    def lista_palavras(self):
        return [p.strip().lower() for p in self.palavras_chave.split(',') if p.strip()]


class TriggerLog(BaseModel):
    trigger = models.ForeignKey(Trigger, on_delete=models.CASCADE, related_name='logs')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='trigger_logs')
    mensagem_recebida = models.TextField(blank=True)
    acoes_executadas = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'log de gatilho'
        verbose_name_plural = 'logs de gatilho'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.trigger.nome} -> {self.contact}'


class ScheduledMsg(BaseModel):
    """Mensagem individual agendada (follow-up) — RF-53, distinta do disparo em massa agendado."""

    STATUS_PENDENTE = 'pendente'
    STATUS_ENVIADA = 'enviada'
    STATUS_CANCELADA = 'cancelada'
    STATUS_FALHA = 'falha'
    STATUS_CHOICES = [
        (STATUS_PENDENTE, 'Pendente'),
        (STATUS_ENVIADA, 'Enviada'),
        (STATUS_CANCELADA, 'Cancelada'),
        (STATUS_FALHA, 'Falha'),
    ]

    ORIGEM_MANUAL = 'manual'
    ORIGEM_GATILHO = 'gatilho'
    ORIGEM_CHOICES = [(ORIGEM_MANUAL, 'Agendado manualmente'), (ORIGEM_GATILHO, 'Agendado por gatilho')]

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='scheduled_messages')
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='scheduled_messages')
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='+')
    data_hora = models.DateTimeField('data e hora do envio')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    origem = models.CharField(max_length=20, choices=ORIGEM_CHOICES, default=ORIGEM_MANUAL)
    erro = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'mensagem agendada'
        verbose_name_plural = 'mensagens agendadas'
        ordering = ['data_hora']
        indexes = [models.Index(fields=['status', 'data_hora'])]

    def __str__(self):
        return f'{self.contact} @ {self.data_hora:%d/%m %H:%M} ({self.status})'
