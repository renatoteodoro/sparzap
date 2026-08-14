from django import forms

from core.forms import apply_input_classes

from .models import AIConfig

FIELD_ORDER = ['nome', 'provider', 'modelo', 'api_key', 'base_url', 'ativo']


class AIConfigForm(forms.ModelForm):
    api_key = forms.CharField(
        label='API key',
        required=False,
        widget=forms.PasswordInput(render_value=False),
    )

    class Meta:
        model = AIConfig
        fields = ['nome', 'provider', 'modelo', 'base_url', 'ativo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        self.order_fields(FIELD_ORDER)
        if self.instance.pk:
            self.fields['api_key'].help_text = 'Deixe em branco para manter a chave atual.'
        else:
            self.fields['api_key'].required = True

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('provider') == AIConfig.PROVIDER_OPENAI_COMPATIVEL and not cleaned_data.get('base_url'):
            self.add_error(
                'base_url',
                'Obrigatório para o provedor "Compatível com OpenAI" (ex.: OpenCode Zen, OpenRouter).',
            )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        nova_chave = self.cleaned_data.get('api_key')
        if nova_chave:
            instance.api_key = nova_chave
        if commit:
            instance.save()
        return instance
