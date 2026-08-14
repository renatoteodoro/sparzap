from django.conf import settings
from django.db import models

from contacts.models import Contact, Group
from core.models import BaseModel
from instances.models import Instance
from scripts.models import Script, ScriptRun


class Campaign(BaseModel):
    STATUS_RASCUNHO = 'rascunho'
    STATUS_AGENDADA = 'agendada'
    STATUS_EM_ANDAMENTO = 'em_andamento'
    STATUS_PAUSADA = 'pausada'
    STATUS_CONCLUIDA = 'concluida'
    STATUS_CANCELADA = 'cancelada'
    STATUS_CHOICES = [
        (STATUS_RASCUNHO, 'Rascunho'),
        (STATUS_AGENDADA, 'Agendada'),
        (STATUS_EM_ANDAMENTO, 'Em andamento'),
        (STATUS_PAUSADA, 'Pausada'),
        (STATUS_CONCLUIDA, 'Concluída'),
        (STATUS_CANCELADA, 'Cancelada'),
    ]

    FILTRO_TODOS = 'todos'
    FILTRO_NAO_RESPONDEU = 'nao_respondeu'
    FILTRO_CHOICES = [
        (FILTRO_TODOS, 'Todos os contatos do público'),
        (FILTRO_NAO_RESPONDEU, 'Somente quem ainda não respondeu'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='campaigns')
    nome = models.CharField('nome', max_length=150)
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='campaigns', verbose_name='instância')
    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name='campaigns', verbose_name='script')

    contatos_avulsos = models.ManyToManyField(Contact, blank=True, related_name='campanhas_avulsas')
    grupos = models.ManyToManyField(Group, blank=True, related_name='campanhas')

    status = models.CharField('status', max_length=20, choices=STATUS_CHOICES, default=STATUS_RASCUNHO)
    agendado_para = models.DateTimeField('agendado para', null=True, blank=True)
    antiduplicacao_dias = models.PositiveIntegerField('anti-duplicação (dias)', default=30)
    filtro_publico = models.CharField('filtro de público', max_length=20, choices=FILTRO_CHOICES, default=FILTRO_TODOS)
    # Nome do campo mantido por compatibilidade (backup/restauração já
    # exportam essa chave); o rótulo mudou porque o comportamento passou a
    # incluir a revalidação de administradores — ver start_campaign.
    remover_admin_antes = models.BooleanField(
        'revalidar administradores dos grupos antes de disparar',
        default=False,
        help_text=(
            'Reconsulta os grupos no WhatsApp antes do envio para garantir que '
            'nenhum administrador receba a mensagem, e remove o próprio bot da '
            'administração dos grupos onde ele for admin.'
        ),
    )

    class Meta:
        verbose_name = 'campanha'
        verbose_name_plural = 'campanhas'
        ordering = ['-created_at']

    def __str__(self):
        return self.nome


class CampaignContact(BaseModel):
    STATUS_PENDENTE = 'pendente'
    STATUS_ENVIADA = 'enviada'
    STATUS_RESPONDIDA = 'respondida'
    STATUS_FALHA = 'falha'
    STATUS_PULADA = 'pulada'
    STATUS_CHOICES = [
        (STATUS_PENDENTE, 'Pendente'),
        (STATUS_ENVIADA, 'Enviada'),
        (STATUS_RESPONDIDA, 'Respondida'),
        (STATUS_FALHA, 'Falha'),
        (STATUS_PULADA, 'Pulada (anti-duplicação/opt-out)'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='campaign_contacts')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='campaign_contacts')
    script_run = models.OneToOneField(
        ScriptRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='campaign_contact'
    )
    status = models.CharField('status', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    origem_grupo = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    enviado_em = models.DateTimeField(null=True, blank=True)
    respondido_em = models.DateTimeField(null=True, blank=True)
    erro = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'contato da campanha'
        verbose_name_plural = 'contatos da campanha'
        constraints = [
            models.UniqueConstraint(fields=['campaign', 'contact'], name='uniq_campaign_contact'),
        ]
        indexes = [models.Index(fields=['campaign', 'status'])]

    def __str__(self):
        return f'{self.contact} @ {self.campaign.nome}'


class DeliveryLog(BaseModel):
    STATUS_ENVIADA = 'enviada'
    STATUS_ENTREGUE = 'entregue'
    STATUS_LIDA = 'lida'
    STATUS_FALHA = 'falha'
    STATUS_CHOICES = [
        (STATUS_ENVIADA, 'Enviada'),
        (STATUS_ENTREGUE, 'Entregue'),
        (STATUS_LIDA, 'Lida'),
        (STATUS_FALHA, 'Falha'),
    ]

    campaign_contact = models.ForeignKey(CampaignContact, on_delete=models.CASCADE, related_name='delivery_logs')
    status = models.CharField('status', max_length=20, choices=STATUS_CHOICES)
    message_id = models.CharField('id da mensagem (Evolution)', max_length=100, blank=True, db_index=True)
    erro = models.TextField(blank=True)

    class Meta:
        verbose_name = 'log de entrega'
        verbose_name_plural = 'logs de entrega'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.status} — {self.campaign_contact}'
