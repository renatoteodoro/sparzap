from django import forms

from core.forms import apply_input_classes
from instances.models import Instance
from library.models import Message

from .models import ScheduledMsg, Trigger


class TriggerForm(forms.ModelForm):
    class Meta:
        model = Trigger
        fields = [
            'nome',
            'instance',
            'palavras_chave',
            'modo',
            'grupo',
            'contato',
            'resposta',
            'etiqueta_nome',
            'etapa_destino',
            'followup_mensagem',
            'followup_apos_horas',
            'prioridade',
            'limite_repeticao_minutos',
            'ativo',
        ]

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        if owner is not None:
            self.fields['instance'].queryset = Instance.objects.filter(owner=owner)
            self.fields['resposta'].queryset = Message.objects.filter(owner=owner)
            self.fields['followup_mensagem'].queryset = Message.objects.filter(owner=owner)
        self.fields['palavras_chave'].widget.attrs['placeholder'] = 'quero, link, preço'


class TriggerTestForm(forms.Form):
    texto = forms.CharField(label='Mensagem simulada', widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)


class ScheduledMsgForm(forms.ModelForm):
    class Meta:
        model = ScheduledMsg
        fields = ['instance', 'message', 'data_hora']
        widgets = {'data_hora': forms.DateTimeInput(attrs={'type': 'datetime-local'})}

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        if owner is not None:
            self.fields['instance'].queryset = Instance.objects.filter(owner=owner)
            self.fields['message'].queryset = Message.objects.filter(owner=owner)
