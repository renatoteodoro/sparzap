from django.conf import settings
from django.db import models

from contacts.models import Contact
from core.models import BaseModel


class Pipeline(BaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pipelines')
    nome = models.CharField('nome', max_length=100)

    class Meta:
        verbose_name = 'pipeline'
        verbose_name_plural = 'pipelines'

    def __str__(self):
        return self.nome


class Stage(BaseModel):
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name='stages')
    nome = models.CharField('nome', max_length=100)
    ordem = models.PositiveIntegerField('ordem', default=0)
    cor = models.CharField('cor', max_length=20, default='gray')
    e_final = models.BooleanField('é etapa final', default=False)

    class Meta:
        verbose_name = 'etapa'
        verbose_name_plural = 'etapas'
        ordering = ['pipeline', 'ordem']
        unique_together = [('pipeline', 'nome')]

    def __str__(self):
        return f'{self.pipeline.nome} / {self.nome}'


class Lead(BaseModel):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='leads')
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name='leads')
    stage = models.ForeignKey(Stage, on_delete=models.PROTECT, related_name='leads')
    origem = models.CharField('origem', max_length=100, blank=True)
    entrou_na_etapa_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'lead'
        verbose_name_plural = 'leads'
        constraints = [
            models.UniqueConstraint(fields=['contact', 'pipeline'], name='uniq_contact_pipeline'),
        ]
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.contact} ({self.stage.nome})'


class LeadNote(BaseModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='notas')
    texto = models.TextField()
    automatica = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'anotação do lead'
        verbose_name_plural = 'anotações do lead'
        ordering = ['-created_at']


class ConversationMessage(BaseModel):
    DIRECAO_ENTRADA = 'entrada'
    DIRECAO_SAIDA = 'saida'
    DIRECAO_CHOICES = [(DIRECAO_ENTRADA, 'Recebida'), (DIRECAO_SAIDA, 'Enviada')]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='mensagens')
    direcao = models.CharField(max_length=10, choices=DIRECAO_CHOICES)
    conteudo = models.TextField(blank=True)

    class Meta:
        verbose_name = 'mensagem da conversa'
        verbose_name_plural = 'mensagens da conversa'
        ordering = ['created_at']
