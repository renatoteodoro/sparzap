from django import forms

from core.forms import apply_input_classes

from .models import Instance


class InstanceForm(forms.ModelForm):
    class Meta:
        model = Instance
        fields = ['nome', 'evolution_instance_name', 'limite_diario', 'janela_inicio', 'janela_fim']
        widgets = {
            'janela_inicio': forms.TimeInput(attrs={'type': 'time'}),
            'janela_fim': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        self.fields['nome'].widget.attrs['placeholder'] = 'Ex.: Vendas 01'
        self.fields['evolution_instance_name'].widget.attrs['placeholder'] = 'ex-vendas-01'
        self.fields['evolution_instance_name'].help_text = 'Identificador único na Evolution API (sem espaços).'


class TestMessageForm(forms.Form):
    numero = forms.CharField(label='Número (com DDI)', max_length=20)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        self.fields['numero'].widget.attrs['placeholder'] = '55DDDNÚMERO'
