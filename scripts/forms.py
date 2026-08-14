from django import forms

from core.forms import apply_input_classes

from .models import Script, ScriptStep


class ScriptForm(forms.ModelForm):
    class Meta:
        model = Script
        fields = ['nome', 'descricao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)


class ScriptStepForm(forms.ModelForm):
    class Meta:
        model = ScriptStep
        fields = [
            'ordem',
            'tipo',
            'message',
            'delay_s',
            'timeout_h',
            'condicao_contem',
            'proximo_passo',
            'etapa_destino',
        ]

    def __init__(self, *args, script=None, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        if script is not None:
            self.fields['proximo_passo'].queryset = script.steps.all()
        if owner is not None:
            from library.models import Message

            self.fields['message'].queryset = Message.objects.filter(owner=owner)


class TestRunForm(forms.Form):
    contact = forms.ModelChoiceField(queryset=None, label='Contato')
    instance = forms.ModelChoiceField(queryset=None, label='Instância')

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        from contacts.models import Contact
        from instances.models import Instance

        if owner is not None:
            self.fields['contact'].queryset = Contact.objects.filter(owner=owner)
            self.fields['instance'].queryset = Instance.objects.filter(owner=owner)
