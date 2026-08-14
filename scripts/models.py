from django.conf import settings
from django.db import models

from contacts.models import Contact
from core.models import BaseModel
from instances.models import Instance
from library.models import Message


class Script(BaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='scripts')
    nome = models.CharField('nome', max_length=150)
    descricao = models.TextField('descrição', blank=True)

    class Meta:
        verbose_name = 'script'
        verbose_name_plural = 'scripts'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class ScriptStep(BaseModel):
    TIPO_MENSAGEM = 'mensagem'
    TIPO_DELAY = 'delay'
    TIPO_AGUARDAR_RESPOSTA = 'aguardar_resposta'
    TIPO_CONDICAO = 'condicao'
    TIPO_MUDAR_ETAPA = 'mudar_etapa'
    TIPO_CHOICES = [
        (TIPO_MENSAGEM, 'Enviar mensagem'),
        (TIPO_DELAY, 'Aguardar (delay fixo)'),
        (TIPO_AGUARDAR_RESPOSTA, 'Aguardar resposta'),
        (TIPO_CONDICAO, 'Condição (se a resposta contiver X)'),
        (TIPO_MUDAR_ETAPA, 'Mudar etapa do lead'),
    ]

    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name='steps')
    ordem = models.PositiveIntegerField('ordem')
    tipo = models.CharField('tipo', max_length=20, choices=TIPO_CHOICES)
    message = models.ForeignKey(
        Message, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name='mensagem'
    )
    delay_s = models.PositiveIntegerField('delay (segundos)', null=True, blank=True)
    timeout_h = models.PositiveIntegerField('timeout (horas)', default=48, null=True, blank=True)
    condicao_contem = models.CharField(
        'resposta contém (separe por vírgula)',
        max_length=255,
        blank=True,
        help_text=(
            'Casa se QUALQUER um dos termos aparecer na resposta. '
            'Maiúsculas e acentos são ignorados — "nao" encontra "Não". '
            'Ex.: nao, nao quero, sem interesse. '
            'Evite termos de 1 ou 2 letras: a busca é por trecho, então "n" '
            'casaria com "mandar".'
        ),
    )
    proximo_passo = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alvo_de',
        verbose_name='próximo passo',
        help_text=(
            'Para onde PULAR se a condição casar (tipo = condição). '
            'Quem não casar segue na ordem normal — por isso condicione nos '
            'termos negativos e pule a mensagem que não deve ser enviada.'
        ),
    )
    usar_ia = models.BooleanField(
        'usar IA para avaliar a condição',
        default=False,
        help_text='Só vale para o tipo "condição". Se a IA falhar, cai no matching por palavra-chave abaixo.',
    )
    ia_config = models.ForeignKey(
        'ai.AIConfig',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='configuração de IA',
    )
    condicao_ia_descricao = models.TextField(
        'descrição para a IA',
        blank=True,
        help_text=(
            'O que conta como positivo — ex.: "o contato demonstrou interesse '
            'em receber o link do grupo".'
        ),
    )
    etapa_destino = models.CharField('etapa destino (crm)', max_length=100, blank=True)

    class Meta:
        verbose_name = 'passo do script'
        verbose_name_plural = 'passos do script'
        ordering = ['script', 'ordem']
        unique_together = [('script', 'ordem')]

    def __str__(self):
        return f'{self.script.nome} #{self.ordem} ({self.get_tipo_display()})'


class ScriptRun(BaseModel):
    """Execução de um Script para um contato — usada tanto pelo 'modo teste' quanto pelos disparos de campanha."""

    STATUS_EM_ANDAMENTO = 'em_andamento'
    STATUS_AGUARDANDO = 'aguardando_resposta'
    STATUS_CONCLUIDO = 'concluido'
    STATUS_CANCELADO = 'cancelado'
    STATUS_ERRO = 'erro'
    STATUS_CHOICES = [
        (STATUS_EM_ANDAMENTO, 'Em andamento'),
        (STATUS_AGUARDANDO, 'Aguardando resposta'),
        (STATUS_CONCLUIDO, 'Concluído'),
        (STATUS_CANCELADO, 'Cancelado'),
        (STATUS_ERRO, 'Erro'),
    ]
    ORIGEM_TESTE = 'teste'
    ORIGEM_CAMPANHA = 'campanha'
    ORIGEM_CHOICES = [
        (ORIGEM_TESTE, 'Teste manual'),
        (ORIGEM_CAMPANHA, 'Campanha'),
    ]

    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name='runs')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='script_runs')
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='script_runs')
    passo_atual = models.ForeignKey(ScriptStep, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    status = models.CharField('status', max_length=20, choices=STATUS_CHOICES, default=STATUS_EM_ANDAMENTO)
    origem = models.CharField('origem', max_length=20, choices=ORIGEM_CHOICES, default=ORIGEM_TESTE)
    aguardando_desde = models.DateTimeField(null=True, blank=True)
    ultimo_message_id = models.CharField(max_length=100, blank=True)
    contexto_extra = models.JSONField(default=dict, blank=True)
    erro = models.TextField(blank=True)

    class Meta:
        verbose_name = 'execução de script'
        verbose_name_plural = 'execuções de script'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['contact', 'status'])]

    def __str__(self):
        return f'{self.script.nome} -> {self.contact} ({self.status})'
