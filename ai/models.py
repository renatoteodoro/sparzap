from django.conf import settings
from django.db import models

from core.models import BaseModel


class AIConfig(BaseModel):
    PROVIDER_ANTHROPIC = 'anthropic'
    PROVIDER_OPENAI = 'openai'
    PROVIDER_GEMINI = 'gemini'
    PROVIDER_OPENAI_COMPATIVEL = 'openai_compativel'
    PROVIDER_CHOICES = [
        (PROVIDER_ANTHROPIC, 'Claude (Anthropic)'),
        (PROVIDER_OPENAI, 'OpenAI'),
        (PROVIDER_GEMINI, 'Google Gemini'),
        (PROVIDER_OPENAI_COMPATIVEL, 'Compatível com OpenAI (URL própria)'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_configs')
    nome = models.CharField('nome', max_length=100)
    provider = models.CharField('provedor', max_length=20, choices=PROVIDER_CHOICES)
    modelo = models.CharField('modelo', max_length=100, help_text='Ex.: claude-opus-5, gpt-5, gemini-2.5-flash.')
    api_key_cifrada = models.TextField('api key (cifrada)')
    base_url = models.CharField(
        'URL base',
        max_length=255,
        blank=True,
        help_text='Obrigatório só para "Compatível com OpenAI" (ex.: OpenCode Zen, OpenRouter).',
    )
    ativo = models.BooleanField('ativo', default=True)

    class Meta:
        verbose_name = 'configuração de IA'
        verbose_name_plural = 'configurações de IA'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.get_provider_display()})'

    @property
    def api_key(self):
        from .crypto import decrypt_api_key

        return decrypt_api_key(self.api_key_cifrada)

    @api_key.setter
    def api_key(self, valor):
        from .crypto import encrypt_api_key

        self.api_key_cifrada = encrypt_api_key(valor)
