from django.conf import settings
from django.db import models

from core.models import BaseModel
from instances.models import Instance


class Tag(BaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tags')
    nome = models.CharField('nome', max_length=50)
    cor = models.CharField('cor', max_length=20, default='gray')

    class Meta:
        verbose_name = 'etiqueta'
        verbose_name_plural = 'etiquetas'
        unique_together = [('owner', 'nome')]
        ordering = ['nome']

    def __str__(self):
        return self.nome


class ContactList(BaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contact_lists')
    nome = models.CharField('nome', max_length=100)
    descricao = models.CharField('descrição', max_length=255, blank=True)

    class Meta:
        verbose_name = 'lista de contatos'
        verbose_name_plural = 'listas de contatos'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Contact(BaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contacts')
    numero_e164 = models.CharField('número (E.164)', max_length=20, db_index=True)
    nome = models.CharField('nome', max_length=150, blank=True)
    opt_out = models.BooleanField('optou por não receber', default=False)
    ultimo_contato = models.DateTimeField('último contato', null=True, blank=True)

    tags = models.ManyToManyField(Tag, through='ContactTag', related_name='contacts', blank=True)
    listas = models.ManyToManyField(ContactList, related_name='contacts', blank=True)

    class Meta:
        verbose_name = 'contato'
        verbose_name_plural = 'contatos'
        constraints = [
            models.UniqueConstraint(fields=['owner', 'numero_e164'], name='uniq_owner_numero'),
        ]
        ordering = ['-ultimo_contato', 'nome']

    def __str__(self):
        return self.nome or self.numero_e164


class ContactTag(BaseModel):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'etiqueta do contato'
        verbose_name_plural = 'etiquetas do contato'
        unique_together = [('contact', 'tag')]


class Group(BaseModel):
    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='groups')
    nome = models.CharField('nome', max_length=150)
    jid = models.CharField('JID', max_length=100, db_index=True)
    membros_count = models.PositiveIntegerField('quantidade de membros', default=0)
    bot_e_admin = models.BooleanField('bot é admin', default=False)

    class Meta:
        verbose_name = 'grupo'
        verbose_name_plural = 'grupos'
        constraints = [
            models.UniqueConstraint(fields=['instance', 'jid'], name='uniq_instance_jid'),
        ]
        ordering = ['nome']

    def __str__(self):
        return self.nome


class GroupMember(BaseModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='membros')
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='grupos')
    jid_participante = models.CharField('JID do participante', max_length=100, blank=True)

    class Meta:
        verbose_name = 'membro do grupo'
        verbose_name_plural = 'membros do grupo'
        unique_together = [('group', 'contact')]


class AdminActionLog(BaseModel):
    """Log do auto-demote (RF-48/6.6.1): remoção do próprio admin do bot num grupo antes do disparo."""

    MODO_AUTOMATICO = 'automatico'
    MODO_MANUAL = 'manual'
    MODO_CHOICES = [(MODO_AUTOMATICO, 'Automático (pré-disparo)'), (MODO_MANUAL, 'Manual')]

    RESULTADO_SUCESSO = 'sucesso'
    RESULTADO_FALHA = 'falha'
    RESULTADO_NAO_ERA_ADMIN = 'nao_era_admin'
    RESULTADO_CHOICES = [
        (RESULTADO_SUCESSO, 'Removido com sucesso'),
        (RESULTADO_FALHA, 'Falha ao remover'),
        (RESULTADO_NAO_ERA_ADMIN, 'Bot já não era admin'),
    ]

    instance = models.ForeignKey(Instance, on_delete=models.CASCADE, related_name='admin_action_logs')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='admin_action_logs')
    modo = models.CharField(max_length=20, choices=MODO_CHOICES)
    resultado = models.CharField(max_length=20, choices=RESULTADO_CHOICES)
    detalhe = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'log de auto-demote'
        verbose_name_plural = 'logs de auto-demote'
        ordering = ['-created_at']

    def __str__(self):
        return f'demote {self.group.nome} ({self.resultado})'
