from django.db import models

from core.models import BaseModel
from instances.models import Instance


class DailyLimit(BaseModel):
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='daily_limits')
    data = models.DateField('data')
    enviadas = models.PositiveIntegerField('enviadas', default=0)

    class Meta:
        verbose_name = 'limite diário'
        verbose_name_plural = 'limites diários'
        constraints = [
            models.UniqueConstraint(fields=['instance', 'data'], name='uniq_instance_data'),
        ]
        ordering = ['-data']

    def __str__(self):
        return f'{self.instance.nome} {self.data}: {self.enviadas}'


class RateSettings(BaseModel):
    instance = models.OneToOneField(Instance, on_delete=models.CASCADE, related_name='rate_settings')
    intervalo_min_s = models.PositiveIntegerField('intervalo mínimo (s)', default=20)
    intervalo_max_s = models.PositiveIntegerField('intervalo máximo (s)', default=60)
    fator_escalonamento = models.FloatField('fator de escalonamento', default=1.0)
    falhas_consecutivas = models.PositiveIntegerField('falhas consecutivas', default=0)

    class Meta:
        verbose_name = 'configuração de ritmo'
        verbose_name_plural = 'configurações de ritmo'

    def __str__(self):
        return f'Ritmo de {self.instance.nome}'


class BlockEvent(BaseModel):
    MOTIVO_RATE_LIMIT = 'rate_limit'
    MOTIVO_FALHAS_CONSECUTIVAS = 'falhas_consecutivas'
    MOTIVO_DESCONECTADO = 'desconectado'
    MOTIVO_LIMITE_DIARIO = 'limite_diario'
    MOTIVO_FORA_JANELA = 'fora_janela'
    MOTIVO_CHOICES = [
        (MOTIVO_RATE_LIMIT, 'Rate limit da Evolution'),
        (MOTIVO_FALHAS_CONSECUTIVAS, 'Falhas consecutivas'),
        (MOTIVO_DESCONECTADO, 'Instância desconectada'),
        (MOTIVO_LIMITE_DIARIO, 'Limite diário atingido'),
        (MOTIVO_FORA_JANELA, 'Fora da janela de operação'),
    ]

    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='block_events')
    motivo = models.CharField('motivo', max_length=30, choices=MOTIVO_CHOICES)
    detalhe = models.CharField('detalhe', max_length=255, blank=True)
    pausou_instancia = models.BooleanField('pausou a instância', default=False)

    class Meta:
        verbose_name = 'evento de bloqueio'
        verbose_name_plural = 'eventos de bloqueio'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_motivo_display()} @ {self.instance.nome}'


class WarmupPlan(BaseModel):
    STATUS_EM_ANDAMENTO = 'em_andamento'
    STATUS_PAUSADO = 'pausado'
    STATUS_CONCLUIDO = 'concluido'
    STATUS_CHOICES = [
        (STATUS_EM_ANDAMENTO, 'Em andamento'),
        (STATUS_PAUSADO, 'Pausado'),
        (STATUS_CONCLUIDO, 'Concluído'),
    ]

    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='warmup_plans')
    inicio = models.DateField('início')
    dias_total = models.PositiveIntegerField('duração (dias)', default=14)
    dia_atual = models.PositiveIntegerField('dia atual', default=1)
    limite_final = models.PositiveIntegerField('limite diário ao final (restaurado)', default=30)
    status = models.CharField('status', max_length=20, choices=STATUS_CHOICES, default=STATUS_EM_ANDAMENTO)

    class Meta:
        verbose_name = 'plano de aquecimento'
        verbose_name_plural = 'planos de aquecimento'
        ordering = ['-created_at']

    def __str__(self):
        return f'Aquecimento {self.instance.nome} — dia {self.dia_atual}/{self.dias_total}'


class WarmupActivity(BaseModel):
    plan = models.ForeignKey(WarmupPlan, on_delete=models.CASCADE, related_name='atividades')
    dia = models.PositiveIntegerField()
    limite_do_dia = models.PositiveIntegerField()

    class Meta:
        verbose_name = 'atividade de aquecimento'
        verbose_name_plural = 'atividades de aquecimento'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.plan.instance.nome} — dia {self.dia} (limite {self.limite_do_dia})'
