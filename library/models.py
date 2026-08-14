from django.conf import settings
from django.db import models

from core.models import BaseModel


class MessageFolder(BaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='message_folders')
    nome = models.CharField('nome', max_length=100)

    class Meta:
        verbose_name = 'pasta de mensagens'
        verbose_name_plural = 'pastas de mensagens'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Message(BaseModel):
    TIPO_TEXTO = 'texto'
    TIPO_AUDIO = 'audio'
    TIPO_IMAGEM = 'imagem'
    TIPO_VIDEO = 'video'
    TIPO_DOCUMENTO = 'documento'
    TIPO_CHOICES = [
        (TIPO_TEXTO, 'Texto'),
        (TIPO_AUDIO, 'Áudio'),
        (TIPO_IMAGEM, 'Imagem'),
        (TIPO_VIDEO, 'Vídeo'),
        (TIPO_DOCUMENTO, 'Documento'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages')
    folder = models.ForeignKey(
        MessageFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='messages',
        verbose_name='pasta',
        help_text='Opcional — serve apenas para organizar a biblioteca.',
    )
    titulo = models.CharField('título', max_length=150)
    tipo = models.CharField('tipo', max_length=20, choices=TIPO_CHOICES, default=TIPO_TEXTO)
    conteudo = models.TextField('conteúdo/legenda', blank=True)
    midia = models.FileField('mídia', upload_to='library/midias/', null=True, blank=True)

    class Meta:
        verbose_name = 'mensagem'
        verbose_name_plural = 'mensagens'
        ordering = ['-created_at']

    def __str__(self):
        return self.titulo

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.tipo != self.TIPO_TEXTO and not self.midia:
            raise ValidationError({'midia': 'Obrigatória para mensagens que não são de texto.'})


class MessageVariant(BaseModel):
    """Variações de texto (spintax) de uma Message — sorteadas a cada envio (RF-26)."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='variants')
    conteudo = models.TextField('conteúdo alternativo')

    class Meta:
        verbose_name = 'variação de mensagem'
        verbose_name_plural = 'variações de mensagem'

    def __str__(self):
        return f'Variação de "{self.message.titulo}"'
