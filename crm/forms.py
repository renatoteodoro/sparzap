from django import forms

from core.forms import apply_input_classes

from .models import LeadNote


class LeadNoteForm(forms.ModelForm):
    class Meta:
        model = LeadNote
        fields = ['texto']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_input_classes(self)
        self.fields['texto'].widget.attrs['placeholder'] = 'Adicionar anotação...'
        self.fields['texto'].widget.attrs['rows'] = 2
