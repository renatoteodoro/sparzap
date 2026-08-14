from django.conf import settings
from django.db import models

from core.models import BaseModel


class Backup(BaseModel):
    TIPO_COMPLETO = 'completo'
    TIPO_SELETIVO = 'seletivo'
    TIPO_CHOICES = [(TIPO_COMPLETO, 'Completo'), (TIPO_SELETIVO, 'Seletivo')]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='backups')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_COMPLETO)
    secoes = models.CharField(max_length=255, blank=True, help_text='Seções incluídas, separadas por vírgula.')
    conteudo = models.JSONField()

    class Meta:
        verbose_name = 'backup'
        verbose_name_plural = 'backups'
        ordering = ['-created_at']

    def __str__(self):
        return f'Backup {self.tipo} de {self.owner} em {self.created_at:%d/%m/%Y %H:%M}'
