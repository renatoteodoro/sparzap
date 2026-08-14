from django import forms

from core.forms import apply_input_classes
from instances.models import Instance

from .backup import SECOES_DISPONIVEIS

SECAO_LABELS = {
    'mensagens': 'Mensagens',
    'scripts': 'Scripts',
    'gatilhos': 'Gatilhos',
    'pipelines': 'Pipelines/etapas',
    'campanhas': 'Campanhas (definição)',
}


class ExportForm(forms.Form):
    secoes = forms.MultipleChoiceField(
        choices=[(s, SECAO_LABELS[s]) for s in SECOES_DISPONIVEIS],
        widget=forms.CheckboxSelectMultiple,
        initial=SECOES_DISPONIVEIS,
    )


class ImportForm(forms.Form):
    CONFLITO_CHOICES = [
        ('ignorar', 'Ignorar duplicados (manter o que já existe)'),
        ('substituir', 'Substituir duplicados'),
        ('renomear', 'Renomear o importado (manter os dois)'),
    ]

    arquivo = forms.FileField(label='Arquivo de backup (.json)')
    target_instance = forms.ModelChoiceField(queryset=None, label='Instância de destino')
    conflito = forms.ChoiceField(choices=CONFLITO_CHOICES, initial='ignorar')

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        if owner is not None:
            self.fields['target_instance'].queryset = Instance.objects.filter(owner=owner)
