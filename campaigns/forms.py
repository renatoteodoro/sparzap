from django import forms

from contacts.models import Contact, Group
from core.forms import apply_input_classes
from instances.models import Instance
from scripts.models import Script

from .models import Campaign


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = [
            'nome',
            'instance',
            'script',
            'contatos_avulsos',
            'grupos',
            'agendado_para',
            'antiduplicacao_dias',
            'filtro_publico',
            'remover_admin_antes',
        ]
        widgets = {
            'agendado_para': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'contatos_avulsos': forms.SelectMultiple,
            'grupos': forms.SelectMultiple,
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        if owner is not None:
            self.fields['instance'].queryset = Instance.objects.filter(owner=owner)
            self.fields['script'].queryset = Script.objects.filter(owner=owner)
            self.fields['contatos_avulsos'].queryset = Contact.objects.filter(owner=owner)
            self.fields['grupos'].queryset = Group.objects.filter(instance__owner=owner)
        self.fields['agendado_para'].required = False
